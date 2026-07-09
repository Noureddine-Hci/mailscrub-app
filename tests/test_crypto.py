"""
Tests du chiffrement des secrets IMAP/POP en session (Fernet, clé dérivée de
SECRET_KEY).
"""

import pytest

from backend.src.security.crypto import decrypt_secret, encrypt_secret

SECRET_KEY = "test-secret-key-not-for-prod"


def test_aller_retour():
    token = encrypt_secret("mon-mot-de-passe-imap", SECRET_KEY)
    assert decrypt_secret(token, SECRET_KEY) == "mon-mot-de-passe-imap"


def test_chiffre_est_illisible():
    token = encrypt_secret("mon-mot-de-passe-imap", SECRET_KEY)
    assert "mon-mot-de-passe-imap" not in token


def test_mauvaise_cle_echoue():
    token = encrypt_secret("mon-mot-de-passe-imap", SECRET_KEY)
    with pytest.raises(ValueError):
        decrypt_secret(token, "une-autre-cle-secrete")


def test_token_falsifie_echoue():
    token = encrypt_secret("mon-mot-de-passe-imap", SECRET_KEY)
    falsifie = token[:-4] + "abcd"
    with pytest.raises(ValueError):
        decrypt_secret(falsifie, SECRET_KEY)


def test_mots_de_passe_avec_caracteres_speciaux():
    mdp = "p@ss w0rd! àéîõü 密码"
    token = encrypt_secret(mdp, SECRET_KEY)
    assert decrypt_secret(token, SECRET_KEY) == mdp
