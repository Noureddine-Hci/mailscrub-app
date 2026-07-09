"""
MailScrub.app — ImapProviderClient

Implémentation IMAP de MailProviderClient. Connexion par mot de passe (pas
d'OAuth) via imaplib (stdlib), toujours en TLS implicite (IMAP4_SSL, port 993
standard chez tous les fournisseurs courants).

Timeout explicite obligatoire sur toute connexion : contrairement aux clients
Google/Graph, imaplib ne timeout JAMAIS par défaut — un hôte saisi par
l'utilisateur qui ne répond pas peut bloquer indéfiniment un worker du
threadpool (voir iterate_in_threadpool dans analysis.py), ce qui affecterait
aussi les requêtes d'autres utilisateurs sur la même instance.

Identifiants UID (pas les numéros de séquence IMAP, qui changent dès qu'un
autre message est supprimé) : seul un UID reste stable pour la durée de vie
du message dans le dossier, indispensable pour que "scanner puis supprimer"
cible bien le même message.
"""

from __future__ import annotations

import imaplib
import re
from email import message_from_bytes
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Iterator

from backend.src.providers.base import DeleteResult, MailProviderClient, MessageSummary
from backend.src.providers.smtp_unsubscribe import send_mailto_unsubscribe

_CONNECT_TIMEOUT = 15  # secondes
_FETCH_CHUNK = 50
_DELETE_CHUNK = 500

# Noms de dossier Corbeille courants, multi-langue — repli si le serveur ne
# déclare pas l'attribut \Trash via l'extension SPECIAL-USE (RFC 6154).
_TRASH_FOLDER_NAMES = {
    "Trash", "Deleted Items", "Deleted Messages", "Corbeille",
    "Papierkorb", "Cestino", "Papelera", "[Gmail]/Trash", "[Gmail]/Corbeille",
}

_UID_RE = re.compile(rb"UID (\d+)")
_SIZE_RE = re.compile(rb"RFC822\.SIZE (\d+)")
_MAILBOX_NAME_RE = re.compile(r'"([^"]*)"$')


def _extract_mailbox_name(list_line: str) -> str | None:
    """Extrait le nom de boîte depuis une ligne de réponse IMAP LIST."""
    match = _MAILBOX_NAME_RE.search(list_line)
    if match:
        return match.group(1)
    parts = list_line.rsplit(" ", 1)
    return parts[-1].strip('"') if parts else None


def _find_trash_folder(conn: imaplib.IMAP4_SSL) -> str | None:
    """
    Cherche un dossier Corbeille via l'attribut \\Trash (RFC 6154) puis, à
    défaut, via une liste de noms courants. None si rien de fiable trouvé —
    l'appelant doit alors traiter la suppression comme définitive (pas de
    filet de sécurité), au même titre que POP3.
    """
    try:
        status, folders = conn.list()
    except Exception:
        return None
    if status != "OK" or not folders:
        return None

    name_candidates = []
    for raw in folders:
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        name = _extract_mailbox_name(line)
        if not name:
            continue
        if "\\Trash" in line:
            return name
        if name in _TRASH_FOLDER_NAMES:
            name_candidates.append(name)

    return name_candidates[0] if name_candidates else None


def _parse_fetch_response(msg_data: list) -> list[MessageSummary]:
    """
    Traduit une réponse `uid('fetch', ...)` en MessageSummary. Fonction pure,
    testable avec une fixture imitant la forme (tuples + bytes) qu'imaplib
    renvoie réellement.
    """
    summaries: list[MessageSummary] = []

    for item in msg_data:
        if not isinstance(item, tuple) or len(item) < 2:
            continue

        meta_line, header_bytes = item[0], item[1]

        uid_match = _UID_RE.search(meta_line)
        if not uid_match:
            continue
        uid = uid_match.group(1).decode("ascii")

        size_match = _SIZE_RE.search(meta_line)
        size_bytes = int(size_match.group(1)) if size_match else 0

        headers = message_from_bytes(header_bytes)
        from_header = headers.get("From", "")
        name, email_addr = parseaddr(from_header)
        email_addr = email_addr.lower().strip()
        if not email_addr:
            continue

        subject = headers.get("Subject", "") or "(Sans objet)"
        list_unsubscribe = headers.get("List-Unsubscribe", "")

        date_header = headers.get("Date", "")
        date_epoch = 0
        if date_header:
            try:
                date_epoch = int(parsedate_to_datetime(date_header).timestamp())
            except (TypeError, ValueError):
                date_epoch = 0

        summaries.append(MessageSummary(
            id=uid,
            from_addr=email_addr,
            from_name=name or email_addr.split("@")[0],
            subject=subject,
            date=date_epoch,
            size_bytes=size_bytes,
            list_unsubscribe=list_unsubscribe,
        ))

    return summaries


class ImapProviderClient(MailProviderClient):
    """Connecteur IMAP générique — hôte/port fournis par l'utilisateur (ou preset)."""

    provider_name = "imap"

    def __init__(
        self, host: str, port: int, username: str, password: str,
        smtp_host: str = "", smtp_port: int = 0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self._host, self._port, timeout=_CONNECT_TIMEOUT)
        conn.login(self._username, self._password)
        return conn

    def verify_connection(self) -> None:
        """Tente une connexion+authentification réelle. Lève une exception si ça échoue."""
        conn = self._connect()
        try:
            conn.logout()
        except Exception:
            pass

    # ── Scan ──────────────────────────────────────────────────

    def scan(self, limit: int) -> Iterator[dict[str, Any]]:
        yield {"type": "progress", "percent": 5, "message": "Connexion IMAP..."}

        try:
            conn = self._connect()
        except Exception as e:
            raise RuntimeError(
                "Impossible de se connecter au serveur IMAP. Vérifiez vos identifiants."
            ) from e

        try:
            status, _ = conn.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("Impossible d'ouvrir la boîte de réception IMAP (INBOX).")

            status, data = conn.uid("search", None, "ALL")
            if status != "OK" or not data or not data[0]:
                yield {"type": "total", "count": 0}
                return

            all_uids = data[0].split()
            # UID croissants = ordre d'arrivée -> les N derniers sont les plus récents.
            selected = all_uids[-limit:] if limit < len(all_uids) else all_uids
            selected = list(reversed(selected))

            total = len(selected)
            yield {"type": "total", "count": total}

            fetched = 0
            for i in range(0, total, _FETCH_CHUNK):
                chunk = selected[i:i + _FETCH_CHUNK]
                uid_set = b",".join(chunk)

                status, msg_data = conn.uid(
                    "fetch", uid_set,
                    "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT LIST-UNSUBSCRIBE DATE)] RFC822.SIZE)",
                )
                fetched += len(chunk)

                if status == "OK":
                    batch_summaries = _parse_fetch_response(msg_data)
                    if batch_summaries:
                        yield {"type": "summary_batch", "data": batch_summaries}
                else:
                    print(f"[WARN] IMAP fetch a échoué pour le lot à l'offset {i}")

                pct = 5 + int((fetched / max(total, 1)) * 85)
                yield {"type": "progress", "percent": min(90, pct), "message": f"Analyse : {fetched}/{total}..."}

        finally:
            try:
                conn.logout()
            except Exception:
                pass

    # ── Unread count ──────────────────────────────────────────

    def count_unread(self) -> int:
        try:
            conn = self._connect()
        except Exception:
            return 0
        try:
            conn.select("INBOX", readonly=True)
            status, data = conn.uid("search", None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return 0
            return len(data[0].split())
        except Exception as e:
            print(f"[WARN] Impossible de récupérer le nombre de non-lus (IMAP): {e}")
            return 0
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    # ── Delete ────────────────────────────────────────────────

    def delete_messages(self, message_ids: list[str], mode: str) -> DeleteResult:
        """
        Déplace vers la Corbeille détectée (COPY + STORE \\Deleted + EXPUNGE)
        si `mode != "delete"` et qu'un dossier Corbeille fiable a été trouvé.
        Sinon (mode "delete", ou pas de Corbeille détectée) : EXPUNGE direct
        sur INBOX — définitif, sans filet de sécurité, comme POP3.
        """
        if not message_ids:
            return DeleteResult(deleted=0, errors=0)

        try:
            conn = self._connect()
        except Exception as e:
            print(f"[WARN] IMAP delete : connexion échouée : {e}")
            return DeleteResult(deleted=0, errors=len(message_ids))

        deleted = 0
        errors = 0
        expunge_failed = False
        try:
            conn.select("INBOX")
            trash_folder = None if mode == "delete" else _find_trash_folder(conn)

            for i in range(0, len(message_ids), _DELETE_CHUNK):
                chunk = message_ids[i:i + _DELETE_CHUNK]
                uid_set = ",".join(chunk).encode("ascii")

                try:
                    if trash_folder:
                        copy_status, _ = conn.uid("copy", uid_set, trash_folder)
                        if copy_status != "OK":
                            # Copie non fiable pour ce lot (et les suivants) : on
                            # repasse en suppression directe plutôt que de risquer
                            # une perte silencieuse (marqué supprimé sans copie).
                            trash_folder = None

                    store_status, _ = conn.uid("store", uid_set, "+FLAGS", "(\\Deleted)")
                    if store_status == "OK":
                        deleted += len(chunk)
                    else:
                        errors += len(chunk)
                except Exception as e:
                    print(f"[WARN] IMAP delete a échoué (lot à l'offset {i}) : {e}")
                    errors += len(chunk)

            try:
                conn.expunge()
            except Exception as e:
                # EXPUNGE committe les STORE \Deleted. S'il échoue, le commit est
                # incertain côté serveur -> on ne compte pas les marquages comme
                # des suppressions réussies (même logique que POP3 QUIT).
                print(f"[WARN] IMAP EXPUNGE a échoué après {deleted} marquages — commit incertain: {e}")
                expunge_failed = True

        except Exception as e:
            print(f"[WARN] IMAP delete : erreur générale : {e}")
            errors += len(message_ids) - deleted - errors
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        if expunge_failed:
            errors += deleted
            deleted = 0

        return DeleteResult(deleted=deleted, errors=errors)

    # ── Unsubscribe (mailto:) ────────────────────────────────

    def send_unsubscribe_mailto(self, to_addr: str, subject: str) -> None:
        send_mailto_unsubscribe(
            self._smtp_host, self._smtp_port, self._username, self._password, to_addr, subject
        )
