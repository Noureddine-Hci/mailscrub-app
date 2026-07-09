"""
MailScrub.app — GoogleProviderClient

Implémentation Gmail de MailProviderClient. Reprend telle quelle la logique
Gmail qui tournait auparavant dans analyzer.py/analysis.py (batching 50/lot,
retry sur 429/5xx, EmailMessage pour le mailto:) — seule sa frontière avec le
driver générique (analyzer.py) change, pas son comportement ni ses
performances.
"""

from __future__ import annotations

import base64
import time
import traceback
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Iterator

from googleapiclient.errors import HttpError

from backend.src.providers.base import DeleteResult, MailProviderClient, MessageSummary

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _execute_with_retry(api_request, max_attempts: int = 4):
    """
    Exécute une requête Gmail (single request) avec retry exponentiel
    sur les erreurs transitoires (429 rate-limit, 5xx).
    """
    delay = 1.0
    for attempt in range(max_attempts):
        try:
            return api_request.execute()
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            try:
                status = int(status)
            except (TypeError, ValueError):
                status = None
            if status in _RETRYABLE_STATUS and attempt < max_attempts - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise


def _parse_metadata_message(msg: dict) -> MessageSummary | None:
    """
    Traduit une réponse brute `messages.get(format="metadata")` en MessageSummary.
    Fonction pure (aucun appel réseau) — testable avec une simple fixture dict.
    Retourne None si le message n'a pas d'expéditeur exploitable.
    """
    msg_id = msg.get("id")
    internal_date = int(msg.get("internalDate", 0)) / 1000

    headers = {
        h["name"]: h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }

    from_header = headers.get("From", "")
    subject = headers.get("Subject", "")

    name, email_addr = parseaddr(from_header)
    email_addr = email_addr.lower().strip()

    if not email_addr:
        return None

    return MessageSummary(
        id=msg_id,
        from_addr=email_addr,
        from_name=name or email_addr.split("@")[0],
        subject=subject or "(Sans objet)",
        date=int(internal_date),
        size_bytes=int(msg.get("sizeEstimate", 0)),
        list_unsubscribe=headers.get("List-Unsubscribe", ""),
    )


class GoogleProviderClient(MailProviderClient):
    """Connecteur Gmail, construit à partir d'un service googleapiclient déjà authentifié."""

    provider_name = "google"

    def __init__(self, service) -> None:
        self._service = service

    # ── Scan ──────────────────────────────────────────────────

    def scan(self, limit: int) -> Iterator[dict[str, Any]]:
        service = self._service

        yield {"type": "progress", "percent": 2, "message": "Récupération de la liste des emails..."}

        # Step 1: List message IDs
        messages: list[dict] = []
        next_page_token = None
        list_error = None
        fetch_limit = limit

        while len(messages) < fetch_limit:
            try:
                results = _execute_with_retry(
                    service.users().messages().list(
                        userId="me",
                        maxResults=100,
                        pageToken=next_page_token,
                    )
                )
            except Exception as e:
                print(f"[WARN] Error fetching message list: {e}")
                list_error = e
                break

            batch = results.get("messages", [])
            if not batch:
                break

            messages.extend(batch)
            next_page_token = results.get("nextPageToken")

            fetched = len(messages)
            pct = 2 + int((fetched / fetch_limit) * 8)
            yield {"type": "progress", "percent": min(10, pct), "message": f"Identifiés : {fetched} emails..."}

            if not next_page_token:
                break

        # Si l'API a échoué AVANT de récupérer le moindre message, c'est une erreur,
        # pas une boîte vide. Sinon (échec tardif avec du contenu déjà en main), on
        # continue avec ce qu'on a — comportement identique à l'ancien code.
        if list_error and not messages:
            raise RuntimeError("Impossible de récupérer vos emails (API Gmail). Réessayez dans un instant.")

        total_emails = len(messages)
        yield {"type": "progress", "percent": 10, "message": f"{total_emails} emails identifiés. Analyse du contenu..."}
        yield {"type": "total", "count": total_emails}

        if total_emails == 0:
            return

        # Step 2: Batch-fetch headers (50 à la fois) — chaque item devient un
        # MessageSummary brut, sans agrégation (le driver s'en charge).
        # `new_batch_http_request` est piloté par callback (push), donc pas
        # moyen de yield depuis l'intérieur : un seul buffer de liste, vidé et
        # réémis en bloc après chaque batch.execute() — pas de renvoi message
        # par message (1000 mails = 20 yields, pas 1000).
        BATCH_SIZE = 50
        effective_limit = min(total_emails, limit)
        collected_batch: list[MessageSummary] = []

        def batch_callback(request_id, response, exception):
            if exception:
                # Erreur individuelle ignorée pour ne pas stopper toute l'analyse.
                print(f"[WARN] Batch item exception: {exception}")
                return

            summary = _parse_metadata_message(response)
            if summary is not None:
                collected_batch.append(summary)

        for i in range(0, effective_limit, BATCH_SIZE):
            batch = service.new_batch_http_request(callback=batch_callback)

            chunk_end = min(i + BATCH_SIZE, effective_limit)
            chunk = messages[i:chunk_end]

            for msg_meta in chunk:
                batch.add(service.users().messages().get(
                    userId="me",
                    id=msg_meta["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "List-Unsubscribe"],
                ))

            collected_batch.clear()
            try:
                batch.execute()
            except Exception as e:
                print(f"[ERROR] Batch execute failed at index {i}: {e}")
                traceback.print_exc()

            if collected_batch:
                yield {"type": "summary_batch", "data": list(collected_batch)}

            pct = 10 + int((chunk_end / effective_limit) * 80)
            yield {"type": "progress", "percent": pct, "message": f"Analyse par lots : {chunk_end}/{effective_limit}..."}

    # ── Unread count ──────────────────────────────────────────

    def count_unread(self) -> int:
        try:
            unread_resp = _execute_with_retry(
                self._service.users().messages().list(
                    userId="me", q="is:unread", maxResults=1
                )
            )
            return int(unread_resp.get("resultSizeEstimate", 0))
        except Exception as e:
            print(f"[WARN] Impossible de récupérer le nombre de non-lus: {e}")
            return 0

    # ── Delete ────────────────────────────────────────────────

    def delete_messages(self, message_ids: list[str], mode: str) -> DeleteResult:
        deleted = 0
        errors = 0

        # Traitement par lots (jusqu'à 1000 IDs/appel) au lieu d'un appel par mail.
        BATCH_SIZE = 1000
        for i in range(0, len(message_ids), BATCH_SIZE):
            chunk = message_ids[i:i + BATCH_SIZE]
            try:
                if mode == "delete":
                    self._service.users().messages().batchDelete(
                        userId="me", body={"ids": chunk}
                    ).execute()
                else:
                    self._service.users().messages().batchModify(
                        userId="me", body={"ids": chunk, "addLabelIds": ["TRASH"]}
                    ).execute()
                deleted += len(chunk)
            except Exception as e:
                print(f"[WARN] Batch {mode} échoué (offset {i}): {e}")
                errors += len(chunk)

        return DeleteResult(deleted=deleted, errors=errors)

    # ── Unsubscribe (mailto:) ────────────────────────────────

    def send_unsubscribe_mailto(self, to_addr: str, subject: str) -> None:
        message = EmailMessage()
        message.set_content("Please unsubscribe me.")
        message["To"] = to_addr
        message["From"] = "me"
        message["Subject"] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}
        self._service.users().messages().send(userId="me", body=create_message).execute()
