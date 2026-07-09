"""
MailScrub.app — MailProvider Interface

Contrat commun que tout connecteur mail (Google, Microsoft, IMAP/POP...) doit
respecter. Le driver générique (backend/src/services/analyzer.py) ne connaît que
cette interface, jamais les détails d'un provider particulier : chaque
implémentation traduit son format fil vers MessageSummary, et c'est tout —
l'agrégation par expéditeur (compteurs, tailles, scoring) vit dans analyzer.py,
écrite une seule fois, partagée par tous les providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class MessageSummary:
    """En-têtes d'un message, indépendants du provider d'origine."""

    id: str
    from_addr: str
    from_name: str
    subject: str
    date: int  # epoch seconds
    size_bytes: int
    list_unsubscribe: str = ""


@dataclass
class DeleteResult:
    """Résultat d'une opération de suppression en lot."""

    deleted: int
    errors: int


class MailProviderClient(ABC):
    """Interface abstraite pour les fournisseurs de messagerie."""

    provider_name: str

    @abstractmethod
    def scan(self, limit: int) -> Iterator[dict[str, Any]]:
        """
        Parcourt la boîte mail et yield des événements :
          - {"type": "progress", "percent": int, "message": str}
          - {"type": "message", "data": MessageSummary}
        """
        ...

    @abstractmethod
    def count_unread(self) -> int:
        """Nombre de mails non lus (estimation acceptable)."""
        ...

    @abstractmethod
    def delete_messages(self, message_ids: list[str], mode: str) -> DeleteResult:
        """Supprime les mails donnés. `mode` : "trash" (réversible) ou "delete" (définitif)."""
        ...

    @abstractmethod
    def send_unsubscribe_mailto(self, to_addr: str, subject: str) -> None:
        """Envoie un e-mail de désabonnement (cas mailto: de List-Unsubscribe)."""
        ...
