"""
MailScrub.app — GmailConnector

Implémentation concrète de MailProvider pour Gmail via l'API Google
et OAuth 2.0. Aucun stockage de données : tout est traité en mémoire.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.core.interfaces import MailProvider

# Scope en lecture seule — on ne modifie RIEN dans la boîte mail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailConnector(MailProvider):
    """
    Connecteur Gmail utilisant l'API Google avec OAuth 2.0.

    Stateless : les données ne sont jamais persistées,
    uniquement traitées en mémoire puis libérées.
    """

    def __init__(self) -> None:
        self._service = None
        self._credentials: Credentials | None = None

    # ── Authentication ────────────────────────────────────────

    def authenticate(self, credentials: dict[str, str]) -> None:
        """
        Lance le flux OAuth 2.0 pour obtenir un token d'accès Gmail.

        Args:
            credentials: Dict avec les clés
                         'client_id' et 'client_secret'.
        """
        client_config = {
            "installed": {
                "client_id": credentials.get(
                    "client_id",
                    os.getenv("GOOGLE_CLIENT_ID", ""),
                ),
                "client_secret": credentials.get(
                    "client_secret",
                    os.getenv("GOOGLE_CLIENT_SECRET", ""),
                ),
                "redirect_uris": [
                    credentials.get(
                        "redirect_uri",
                        os.getenv(
                            "GOOGLE_REDIRECT_URI",
                            "http://localhost:8080/oauth/callback",
                        ),
                    )
                ],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        self._credentials = flow.run_local_server(port=0)
        self._service = build("gmail", "v1", credentials=self._credentials)

    # ── Fetch Messages (headers only) ─────────────────────────

    def fetch_messages(
        self,
        max_results: int = 500,
        query: str = "",
    ) -> list[dict[str, Any]]:
        """
        Récupère les en-têtes des messages Gmail.

        Seuls les champs 'From', 'Subject', 'Date' sont extraits
        pour identifier les expéditeurs — le corps du mail n'est
        JAMAIS téléchargé (Stateless / Privacy-first).
        """
        if not self._service:
            raise RuntimeError(
                "Non authentifié. Appelez authenticate() d'abord."
            )

        messages_metadata: list[dict[str, Any]] = []
        page_token: str | None = None

        while len(messages_metadata) < max_results:
            batch_size = min(100, max_results - len(messages_metadata))

            # 1. Lister les IDs de messages
            response = (
                self._service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=batch_size,
                    q=query or None,
                    pageToken=page_token,
                )
                .execute()
            )

            message_ids = response.get("messages", [])
            if not message_ids:
                break

            # 2. Pour chaque ID, récupérer uniquement les headers
            for msg_ref in message_ids:
                msg = (
                    self._service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_ref["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )

                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }

                messages_metadata.append(
                    {
                        "id": msg_ref["id"],
                        "from": headers.get("From", ""),
                        "subject": headers.get("Subject", ""),
                        "date": headers.get("Date", ""),
                    }
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return messages_metadata

    # ── Top Senders ───────────────────────────────────────────

    def get_top_senders(self, top_n: int = 10) -> list[tuple[str, int]]:
        """
        Analyse les messages et retourne les N expéditeurs
        les plus fréquents. Rien n'est stocké : on parcourt,
        on compte, on retourne.

        Args:
            top_n: Nombre d'expéditeurs à afficher (défaut: 10).

        Returns:
            Liste de tuples (email, count) triée par fréquence desc.
        """
        messages = self.fetch_messages()

        # Compter les occurrences de chaque expéditeur
        sender_counter: Counter[str] = Counter()

        for msg in messages:
            sender = msg.get("from", "")
            # Nettoyer : "John Doe <john@example.com>" → "john@example.com"
            if "<" in sender and ">" in sender:
                sender = sender.split("<")[1].rstrip(">")
            sender = sender.strip().lower()

            if sender:
                sender_counter[sender] += 1

        return sender_counter.most_common(top_n)
