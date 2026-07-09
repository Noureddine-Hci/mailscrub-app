"""
MailScrub.app — Envoi SMTP pour le désabonnement mailto: (IMAP/POP)

IMAP et POP3 sont des protocoles de lecture/gestion — aucun des deux ne sait
envoyer un mail. Le cas mailto: de List-Unsubscribe (voir routers/analysis.py)
a donc besoin d'un canal SMTP séparé, avec les mêmes identifiants. Partagé
entre ImapProviderClient et PopProviderClient (mécanisme identique une fois
qu'on a host/port/username/password).
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

_CONNECT_TIMEOUT = 15  # secondes — smtplib ne timeout jamais par défaut


def send_mailto_unsubscribe(
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    to_addr: str,
    subject: str,
) -> None:
    """Envoie l'e-mail de désabonnement. Lève une exception si l'envoi échoue."""
    if not smtp_host or not smtp_port:
        raise RuntimeError(
            "Aucun serveur SMTP configuré pour ce compte — désabonnement par email impossible."
        )

    message = EmailMessage()
    message.set_content("Please unsubscribe me.")
    message["To"] = to_addr
    message["From"] = username
    message["Subject"] = subject

    # 465 = TLS implicite (SMTPS) ; tout le reste (587, 25, ...) = STARTTLS.
    # Les deux modes coexistent dans la nature (pas de convention universelle) —
    # on choisit sur le port plutôt que de figer un seul mode.
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=_CONNECT_TIMEOUT) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=_CONNECT_TIMEOUT) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
