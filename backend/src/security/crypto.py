"""
MailScrub.app — Chiffrement des secrets IMAP/POP en session

Le cookie de session est SIGNÉ (itsdangerous) mais PAS chiffré : son contenu
est lisible en base64 par quiconque possède le cookie, seule sa falsification
est empêchée. Pour Google/Microsoft ce n'est pas un problème : on n'y stocke
que des tokens OAuth (révocables, portée limitée, jamais le client_secret de
l'app). Pour IMAP/POP, le "token" est le vrai mot de passe de la boîte mail de
l'utilisateur — un secret qu'on ne peut pas se permettre de laisser lisible en
clair. D'où cette dérogation ciblée et documentée à la règle "aucun secret
dans le cookie" : SEUL ce champ est chiffré (Fernet), le reste de la session
reste signé comme avant.

Clé dérivée de SECRET_KEY (déjà obligatoire en prod, voir main.py) plutôt
qu'une variable d'env supplémentaire à gérer/faire tourner séparément. Une
rotation de SECRET_KEY invalide donc les deux couches en même temps — la
signature itsdangerous échoue avant même d'atteindre la couche Fernet.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _derive_fernet_key(secret_key: str) -> bytes:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str, secret_key: str) -> str:
    """Chiffre `plaintext` (ex. mot de passe IMAP/POP) pour stockage en session."""
    fernet = Fernet(_derive_fernet_key(secret_key))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str, secret_key: str) -> str:
    """
    Déchiffre un secret précédemment chiffré par encrypt_secret().
    Lève ValueError si le token est invalide/corrompu/falsifié.

    Pas de `ttl=` ici volontairement : l'expiration de la session (donc du
    cookie qui porte ce token) est déjà gérée par SessionMiddleware — inutile
    de faire dériver deux horloges d'expiration indépendantes.
    """
    fernet = Fernet(_derive_fernet_key(secret_key))
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Secret de session invalide ou corrompu.") from e
