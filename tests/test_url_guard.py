"""
Tests de la garde SSRF utilisée par /api/unsubscribe.
On teste les cas déterministes (schémas, IP littérales) sans dépendre du DNS.
"""

from backend.routers.analysis import _is_safe_public_url


def test_rejette_schemas_non_http():
    assert _is_safe_public_url("ftp://example.com/x") is False
    assert _is_safe_public_url("mailto:unsub@example.com") is False


def test_bloque_loopback_et_ip_privees():
    assert _is_safe_public_url("http://127.0.0.1:8000/x") is False
    assert _is_safe_public_url("http://10.0.0.5/x") is False
    assert _is_safe_public_url("http://192.168.1.1/x") is False
    # Serveur de métadonnées cloud (link-local)
    assert _is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False


def test_rejette_entrees_invalides():
    assert _is_safe_public_url("pas une url") is False
    assert _is_safe_public_url("") is False
