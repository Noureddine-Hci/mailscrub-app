"""
Tests du mapping Gmail -> MessageSummary (logique pure, sans API Gmail).
Fixture façon réponse réelle de messages.get(format="metadata").
"""

from backend.src.providers.base import MessageSummary
from backend.src.providers.google_provider import _parse_metadata_message


def _fixture(headers: list[dict], **overrides) -> dict:
    msg = {
        "id": "18abc123",
        "internalDate": "1718000000000",  # ms
        "sizeEstimate": 10240,
        "payload": {"headers": headers},
    }
    msg.update(overrides)
    return msg


def test_parse_message_simple():
    msg = _fixture([
        {"name": "From", "value": "Marie Dupont <marie.dupont@gmail.com>"},
        {"name": "Subject", "value": "Coucou"},
    ])
    summary = _parse_metadata_message(msg)

    assert isinstance(summary, MessageSummary)
    assert summary.id == "18abc123"
    assert summary.from_addr == "marie.dupont@gmail.com"
    assert summary.from_name == "Marie Dupont"
    assert summary.subject == "Coucou"
    assert summary.date == 1718000000
    assert summary.size_bytes == 10240
    assert summary.list_unsubscribe == ""


def test_parse_message_avec_list_unsubscribe():
    msg = _fixture([
        {"name": "From", "value": "Medium Daily Digest <newsletter@medium.com>"},
        {"name": "Subject", "value": "Votre digest"},
        {"name": "List-Unsubscribe", "value": "<https://medium.com/unsub>"},
    ])
    summary = _parse_metadata_message(msg)

    assert summary.from_addr == "newsletter@medium.com"
    assert summary.list_unsubscribe == "<https://medium.com/unsub>"


def test_parse_message_sans_nom_utilise_partie_locale():
    msg = _fixture([
        {"name": "From", "value": "noreply@github.com"},
    ])
    summary = _parse_metadata_message(msg)

    assert summary.from_name == "noreply"


def test_parse_message_sans_objet():
    msg = _fixture([
        {"name": "From", "value": "jean@free.fr"},
    ])
    summary = _parse_metadata_message(msg)

    assert summary.subject == "(Sans objet)"


def test_parse_message_sans_expediteur_retourne_none():
    msg = _fixture([
        {"name": "Subject", "value": "Pas d'expéditeur exploitable"},
    ])
    assert _parse_metadata_message(msg) is None
