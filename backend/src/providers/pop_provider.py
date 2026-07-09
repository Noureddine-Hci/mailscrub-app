"""
MailScrub.app — PopProviderClient

Implémentation POP3 de MailProviderClient. Protocole beaucoup plus limité
qu'IMAP :
  - Pas de dossiers, pas de fetch groupé (TOP par message, un aller-retour
    chacun) -> plafond de scan dédié (_MAX_SCAN), indépendant du sélecteur
    500/1000/2500/5000 du frontend.
  - PAS de corbeille : DELE marque, QUIT committe — définitif et irréversible
    pour ce compte. Le frontend impose un avertissement fort dédié avant
    d'appeler delete_messages() pour un compte POP3 (décision produit actée).
  - Pas de notion de lu/non-lu côté serveur -> count_unread() retourne 0.

Timeout explicite obligatoire (mêmes raisons que ImapProviderClient : poplib
ne timeout jamais par défaut).

Identifiants : UIDL (RFC 1939) plutôt que les numéros de message bruts, qui
ne sont valides que pour la session POP3 en cours et se décalent après toute
suppression — UIDL reste stable tant que le message existe sur le serveur.
"""

from __future__ import annotations

import poplib
from email import message_from_bytes
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Iterator

from backend.src.providers.base import DeleteResult, MailProviderClient, MessageSummary
from backend.src.providers.smtp_unsubscribe import send_mailto_unsubscribe

_CONNECT_TIMEOUT = 15  # secondes
_MAX_SCAN = 300
_YIELD_EVERY = 20  # taille de lot pour les événements summary_batch


def _parse_top_response(uid: str, lines: list[bytes]) -> MessageSummary | None:
    """Traduit les lignes d'en-têtes renvoyées par TOP en MessageSummary. Fonction pure."""
    raw = b"\r\n".join(lines)
    headers = message_from_bytes(raw)

    from_header = headers.get("From", "")
    name, email_addr = parseaddr(from_header)
    email_addr = email_addr.lower().strip()
    if not email_addr:
        return None

    subject = headers.get("Subject", "") or "(Sans objet)"
    list_unsubscribe = headers.get("List-Unsubscribe", "")

    date_header = headers.get("Date", "")
    date_epoch = 0
    if date_header:
        try:
            date_epoch = int(parsedate_to_datetime(date_header).timestamp())
        except (TypeError, ValueError):
            date_epoch = 0

    return MessageSummary(
        id=uid,
        from_addr=email_addr,
        from_name=name or email_addr.split("@")[0],
        subject=subject,
        date=date_epoch,
        size_bytes=0,  # renseigné séparément via LIST, voir scan()
        list_unsubscribe=list_unsubscribe,
    )


class PopProviderClient(MailProviderClient):
    """Connecteur POP3 générique — hôte/port fournis par l'utilisateur (ou preset)."""

    provider_name = "pop3"

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

    def _connect(self) -> poplib.POP3_SSL:
        conn = poplib.POP3_SSL(self._host, self._port, timeout=_CONNECT_TIMEOUT)
        conn.user(self._username)
        conn.pass_(self._password)
        return conn

    def verify_connection(self) -> None:
        """Tente une connexion+authentification réelle. Lève une exception si ça échoue."""
        conn = self._connect()
        try:
            conn.quit()
        except Exception:
            pass

    def _list_uid_pairs(self, conn: poplib.POP3_SSL) -> list[tuple[int, str]]:
        """Retourne [(numéro de session, UIDL), ...]. Repli sur le numéro de
        session si le serveur ne supporte pas UIDL (rare mais possible)."""
        try:
            _, uid_lines, _ = conn.uidl()
            pairs = []
            for line in uid_lines:
                num_b, uid_b = line.split(maxsplit=1)
                pairs.append((int(num_b), uid_b.decode("ascii", errors="replace")))
            return pairs
        except poplib.error_proto:
            count, _ = conn.stat()
            return [(n, str(n)) for n in range(1, count + 1)]

    # ── Scan ──────────────────────────────────────────────────

    def scan(self, limit: int) -> Iterator[dict[str, Any]]:
        yield {"type": "progress", "percent": 5, "message": "Connexion POP3..."}

        try:
            conn = self._connect()
        except Exception as e:
            raise RuntimeError(
                "Impossible de se connecter au serveur POP3. Vérifiez vos identifiants."
            ) from e

        try:
            effective_limit = min(limit, _MAX_SCAN)
            pairs = self._list_uid_pairs(conn)

            # Numéros de session croissants = ordre d'arrivée -> les derniers
            # sont les plus récents.
            selected = pairs[-effective_limit:] if effective_limit < len(pairs) else pairs
            selected = list(reversed(selected))

            total = len(selected)
            yield {"type": "total", "count": total}

            fetched = 0
            batch: list[MessageSummary] = []
            for msg_num, uid in selected:
                try:
                    _, lines, _ = conn.top(msg_num, 0)
                    summary = _parse_top_response(uid, lines)
                    if summary is not None:
                        try:
                            _, list_line, _ = conn.list(msg_num)
                            summary.size_bytes = int(list_line.split()[1])
                        except Exception:
                            pass
                        batch.append(summary)
                except poplib.error_proto as e:
                    print(f"[WARN] POP3 TOP a échoué pour le message {msg_num}: {e}")

                fetched += 1

                if len(batch) >= _YIELD_EVERY:
                    yield {"type": "summary_batch", "data": batch}
                    batch = []

                if fetched % 10 == 0 or fetched == total:
                    pct = 5 + int((fetched / max(total, 1)) * 85)
                    yield {"type": "progress", "percent": min(90, pct), "message": f"Analyse : {fetched}/{total}..."}

            if batch:
                yield {"type": "summary_batch", "data": batch}

        finally:
            try:
                conn.quit()
            except Exception:
                pass

    # ── Unread count ──────────────────────────────────────────

    def count_unread(self) -> int:
        # POP3 n'a pas de flag \Seen côté serveur — pas de valeur inventée.
        return 0

    # ── Delete ────────────────────────────────────────────────

    def delete_messages(self, message_ids: list[str], mode: str) -> DeleteResult:
        """
        DELE + QUIT — définitif et irréversible (pas de corbeille en POP3),
        quel que soit `mode`. Le frontend affiche un avertissement dédié avant
        d'appeler cette action pour un compte POP3.
        """
        if not message_ids:
            return DeleteResult(deleted=0, errors=0)

        try:
            conn = self._connect()
        except Exception as e:
            print(f"[WARN] POP3 delete : connexion échouée : {e}")
            return DeleteResult(deleted=0, errors=len(message_ids))

        deleted = 0
        errors = 0
        quit_failed = False

        try:
            pairs = self._list_uid_pairs(conn)
            uid_to_num = {uid: num for num, uid in pairs}

            for msg_id in message_ids:
                msg_num = uid_to_num.get(msg_id)
                if msg_num is None:
                    errors += 1
                    continue
                try:
                    conn.dele(msg_num)
                    deleted += 1
                except poplib.error_proto as e:
                    print(f"[WARN] POP3 DELE a échoué pour {msg_id}: {e}")
                    errors += 1

            try:
                conn.quit()
            except Exception as e:
                # QUIT committe les DELE (RFC 1939). S'il échoue, le commit est
                # incertain côté serveur -> on ne compte pas les DELE comme
                # réussis.
                print(f"[WARN] POP3 QUIT a échoué après {deleted} DELE — commit incertain: {e}")
                quit_failed = True

        except Exception as e:
            print(f"[WARN] POP3 delete : erreur générale : {e}")
            errors += len(message_ids) - deleted - errors
            try:
                conn.quit()
            except Exception:
                pass

        if quit_failed:
            errors += deleted
            deleted = 0

        return DeleteResult(deleted=deleted, errors=errors)

    # ── Unsubscribe (mailto:) ────────────────────────────────

    def send_unsubscribe_mailto(self, to_addr: str, subject: str) -> None:
        send_mailto_unsubscribe(
            self._smtp_host, self._smtp_port, self._username, self._password, to_addr, subject
        )
