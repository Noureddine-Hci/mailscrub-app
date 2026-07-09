"""
MailScrub.app — MicrosoftProviderClient

Implémentation Outlook/Microsoft 365 de MailProviderClient, via Microsoft
Graph (REST) et un access token déjà valide obtenu par MSAL (voir
backend/routers/auth.py).

⚠️ Points non vérifiés contre un vrai tenant Azure (pas d'App Registration
disponible pour tester en développement) :
  - `internetMessageHeaders` est documenté comme lisible sur un message
    individuel ; son comportement exact via `$select` sur l'endpoint de LISTE
    paginée (/me/messages) n'a pas été confirmé en conditions réelles. Si les
    headers reviennent vides sur la liste, il faudra un second appel par lot
    (Graph JSON batching, POST /$batch, ~20 sous-requêtes par lot) — même
    schéma à deux phases que Gmail. Non implémenté tant que le premier
    comportement n'est pas invalidé par un test réel.
  - Graph n'expose pas de taille en octets directement sur /me/messages (pas
    d'équivalent au `sizeEstimate` de Gmail) : `size_bytes` reste à 0 pour ce
    provider. Conséquence : les suggestions "gros fichiers / vieux mails" et
    le récapitulatif d'espace ne se déclenchent pas pour les comptes Outlook.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterator

import msal
import requests

from backend.src.providers.base import DeleteResult, MailProviderClient, MessageSummary

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TIMEOUT = 15  # secondes — pas de valeur par défaut côté `requests`, danger de hang sinon
_PAGE_SIZE = 50
_DELETE_BATCH_SIZE = 20  # limite documentée de Graph $batch (v1.0)

_SELECT_FIELDS = "subject,from,receivedDateTime,internetMessageHeaders"

# Scopes Graph + config MSAL — définis ici (pas dans routers/auth.py) car
# nécessaires à la fois pour le login initial (auth.py) ET le rafraîchissement
# de token (analysis.py) : co-localisés avec le provider plutôt que dupliqués
# ou importés d'un router vers l'autre.
MICROSOFT_SCOPES = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
]
MICROSOFT_AUTHORITY = "https://login.microsoftonline.com/common"


def get_msal_app() -> msal.ConfidentialClientApplication:
    """Crée le client MSAL à partir des identifiants Azure App Registration (env)."""
    return msal.ConfidentialClientApplication(
        client_id=os.getenv("MICROSOFT_CLIENT_ID"),
        client_credential=os.getenv("MICROSOFT_CLIENT_SECRET"),
        authority=MICROSOFT_AUTHORITY,
    )


def _parse_graph_datetime(value: str) -> int:
    """receivedDateTime est un ISO 8601 UTC, ex. "2026-01-01T12:00:00Z"."""
    if not value:
        return 0
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return 0
    return int(dt.timestamp())


def _parse_graph_message(msg: dict) -> MessageSummary | None:
    """Traduit un message Graph (/me/messages) en MessageSummary. Fonction pure, testable."""
    from_field = (msg.get("from") or {}).get("emailAddress") or {}
    email_addr = (from_field.get("address") or "").lower().strip()
    if not email_addr:
        return None

    name = from_field.get("name") or email_addr.split("@")[0]
    subject = msg.get("subject") or "(Sans objet)"

    list_unsubscribe = ""
    for header in msg.get("internetMessageHeaders") or []:
        if (header.get("name") or "").lower() == "list-unsubscribe":
            list_unsubscribe = header.get("value", "")
            break

    return MessageSummary(
        id=msg.get("id", ""),
        from_addr=email_addr,
        from_name=name,
        subject=subject,
        date=_parse_graph_datetime(msg.get("receivedDateTime", "")),
        size_bytes=0,  # voir note de module — pas de champ taille fiable côté Graph
        list_unsubscribe=list_unsubscribe,
    )


class MicrosoftProviderClient(MailProviderClient):
    """Connecteur Outlook/Microsoft 365, construit à partir d'un access token Graph valide."""

    provider_name = "microsoft"

    def __init__(self, access_token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    # ── Scan ──────────────────────────────────────────────────

    def scan(self, limit: int) -> Iterator[dict[str, Any]]:
        yield {"type": "progress", "percent": 5, "message": "Récupération des emails (Outlook)..."}

        url = f"{GRAPH_BASE}/me/messages"
        params = {"$select": _SELECT_FIELDS, "$top": _PAGE_SIZE}
        fetched = 0
        first_page = True

        while url and fetched < limit:
            try:
                resp = requests.get(
                    url,
                    headers=self._headers,
                    params=params if first_page else None,
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                if fetched == 0:
                    raise RuntimeError(
                        "Impossible de récupérer vos emails (API Microsoft Graph). Réessayez dans un instant."
                    ) from e
                # Echec tardif avec du contenu déjà en main : on continue avec ce qu'on a.
                print(f"[WARN] Graph messages.list a échoué après {fetched} mails : {e}")
                break

            first_page = False
            data = resp.json()
            page_messages = data.get("value", [])

            batch_summaries: list[MessageSummary] = []
            for msg in page_messages:
                if fetched >= limit:
                    break
                summary = _parse_graph_message(msg)
                fetched += 1
                if summary is not None:
                    batch_summaries.append(summary)

            if batch_summaries:
                yield {"type": "summary_batch", "data": batch_summaries}

            pct = 5 + int((fetched / max(limit, 1)) * 85)
            yield {"type": "progress", "percent": min(90, pct), "message": f"Analyse : {fetched}/{limit}..."}

            # @odata.nextLink est une URL complète prête à l'emploi — on la
            # réutilise telle quelle, sans reconstruire les query params.
            url = data.get("@odata.nextLink")

        yield {"type": "total", "count": fetched}

    # ── Unread count ──────────────────────────────────────────

    def count_unread(self) -> int:
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/me/mailFolders/inbox",
                headers=self._headers,
                params={"$select": "unreadItemCount"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return int(resp.json().get("unreadItemCount", 0))
        except requests.RequestException as e:
            print(f"[WARN] Impossible de récupérer le nombre de non-lus (Graph): {e}")
            return 0

    # ── Delete ────────────────────────────────────────────────

    def delete_messages(self, message_ids: list[str], mode: str) -> DeleteResult:
        """
        Graph ne propose pas de suppression définitive en un seul appel : DELETE
        déplace vers "Deleted Items" (équivalent trash), quel que soit `mode`.
        """
        deleted = 0
        errors = 0

        for i in range(0, len(message_ids), _DELETE_BATCH_SIZE):
            chunk = message_ids[i:i + _DELETE_BATCH_SIZE]
            batch_body = {
                "requests": [
                    {"id": str(j), "method": "DELETE", "url": f"/me/messages/{msg_id}"}
                    for j, msg_id in enumerate(chunk)
                ]
            }
            try:
                resp = requests.post(
                    f"{GRAPH_BASE}/$batch",
                    headers=self._headers,
                    json=batch_body,
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                responses = resp.json().get("responses", [])
                for r in responses:
                    status = r.get("status", 500)
                    if 200 <= status < 300:
                        deleted += 1
                    else:
                        errors += 1
                # Réponses manquantes pour certains items du lot -> comptées en erreur.
                errors += max(0, len(chunk) - len(responses))
            except requests.RequestException as e:
                print(f"[WARN] Graph $batch delete échoué (offset {i}): {e}")
                errors += len(chunk)

        return DeleteResult(deleted=deleted, errors=errors)

    # ── Unsubscribe (mailto:) ────────────────────────────────

    def send_unsubscribe_mailto(self, to_addr: str, subject: str) -> None:
        body = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": "Please unsubscribe me."},
                "toRecipients": [{"emailAddress": {"address": to_addr}}],
            },
            "saveToSentItems": "false",
        }
        resp = requests.post(
            f"{GRAPH_BASE}/me/sendMail",
            headers=self._headers,
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
