"""
MailScrub.app — MailProvider Interface (Abstract Base Class)

Cette classe définit le contrat que TOUT connecteur mail doit respecter.
Architecture modulaire : ajouter Outlook ou IMAP revient simplement à
créer une nouvelle classe qui hérite de MailProvider.
"""

from abc import ABC, abstractmethod
from typing import Any


class MailProvider(ABC):
    """Interface abstraite pour les fournisseurs de messagerie."""

    @abstractmethod
    def authenticate(self, credentials: dict[str, str]) -> None:
        """Authentifie l'utilisateur auprès du fournisseur de mail."""
        ...

    @abstractmethod
    def fetch_messages(
        self,
        max_results: int = 500,
        query: str = "",
    ) -> list[dict[str, Any]]:
        """Récupère les en-têtes des messages (sans le corps). Stateless."""
        ...

    @abstractmethod
    def get_top_senders(self, top_n: int = 10) -> list[tuple[str, int]]:
        """Retourne les N expéditeurs les plus fréquents."""
        ...
