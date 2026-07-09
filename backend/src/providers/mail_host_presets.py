"""
MailScrub.app — Presets hôtes IMAP/POP/SMTP par domaine

Préremplit le formulaire de connexion IMAP/POP pour les fournisseurs courants
(confort utilisateur uniquement). Un domaine absent de cette table reste
utilisable via la saisie manuelle hôte/port du formulaire.

Ports SMTP tous en 587/STARTTLS (RFC 6409, "submission") plutôt que 465 —
port le plus universellement supporté, évite de parier sur le support de
465/TLS-implicite par tel ou tel fournisseur sans pouvoir le vérifier ici.
"""

from __future__ import annotations

_PRESETS: dict[str, dict[str, object]] = {
    "gmail.com": {
        "imap_host": "imap.gmail.com", "imap_port": 993,
        "pop_host": "pop.gmail.com", "pop_port": 995,
        "smtp_host": "smtp.gmail.com", "smtp_port": 587,
    },
    "outlook.com": {
        "imap_host": "outlook.office365.com", "imap_port": 993,
        "pop_host": "outlook.office365.com", "pop_port": 995,
        "smtp_host": "smtp.office365.com", "smtp_port": 587,
    },
    "hotmail.com": {
        "imap_host": "outlook.office365.com", "imap_port": 993,
        "pop_host": "outlook.office365.com", "pop_port": 995,
        "smtp_host": "smtp.office365.com", "smtp_port": 587,
    },
    "live.com": {
        "imap_host": "outlook.office365.com", "imap_port": 993,
        "pop_host": "outlook.office365.com", "pop_port": 995,
        "smtp_host": "smtp.office365.com", "smtp_port": 587,
    },
    "yahoo.com": {
        "imap_host": "imap.mail.yahoo.com", "imap_port": 993,
        "pop_host": "pop.mail.yahoo.com", "pop_port": 995,
        "smtp_host": "smtp.mail.yahoo.com", "smtp_port": 587,
    },
    "icloud.com": {
        "imap_host": "imap.mail.me.com", "imap_port": 993,
        # iCloud ne supporte pas POP3.
        "pop_host": None, "pop_port": None,
        "smtp_host": "smtp.mail.me.com", "smtp_port": 587,
    },
}


def get_preset(email_addr: str) -> dict[str, object] | None:
    """Retourne le preset hôtes pour le domaine de `email_addr`, ou None si inconnu."""
    if "@" not in email_addr:
        return None
    domain = email_addr.rsplit("@", 1)[1].strip().lower()
    return _PRESETS.get(domain)


def all_presets() -> dict[str, dict[str, object]]:
    """Retourne tous les presets (pour GET /auth/imap/presets)."""
    return _PRESETS
