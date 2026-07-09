"""
Tests du mapping Microsoft Graph -> MessageSummary (logique pure, sans API).
Fixture façon réponse réelle de GET /me/messages (docs Microsoft Graph).
"""

from datetime import datetime, timezone

from backend.src.providers.base import MessageSummary
from backend.src.providers.microsoft_provider import _parse_graph_datetime, _parse_graph_message

_EXPECTED_EPOCH = int(datetime(2026, 6, 1, 8, 30, 0, tzinfo=timezone.utc).timestamp())


def _fixture(**overrides) -> dict:
    msg = {
        "id": "AAMkAGI2THVSAAA=",
        "subject": "Votre digest",
        "receivedDateTime": "2026-06-01T08:30:00Z",
        "from": {
            "emailAddress": {"name": "Medium Daily Digest", "address": "newsletter@medium.com"}
        },
        "internetMessageHeaders": [
            {"name": "X-Mailer", "value": "Medium"},
            {"name": "List-Unsubscribe", "value": "<https://medium.com/unsub>"},
        ],
    }
    msg.update(overrides)
    return msg


def test_parse_message_simple():
    summary = _parse_graph_message(_fixture())

    assert isinstance(summary, MessageSummary)
    assert summary.id == "AAMkAGI2THVSAAA="
    assert summary.from_addr == "newsletter@medium.com"
    assert summary.from_name == "Medium Daily Digest"
    assert summary.subject == "Votre digest"
    assert summary.list_unsubscribe == "<https://medium.com/unsub>"
    assert summary.size_bytes == 0  # pas d'équivalent Graph au sizeEstimate Gmail


def test_parse_message_sans_list_unsubscribe():
    msg = _fixture(internetMessageHeaders=[{"name": "X-Mailer", "value": "Medium"}])
    summary = _parse_graph_message(msg)
    assert summary.list_unsubscribe == ""


def test_parse_message_sans_headers():
    msg = _fixture(internetMessageHeaders=None)
    summary = _parse_graph_message(msg)
    assert summary.list_unsubscribe == ""


def test_parse_message_sans_nom_utilise_partie_locale():
    msg = _fixture(**{"from": {"emailAddress": {"address": "noreply@github.com"}}})
    summary = _parse_graph_message(msg)
    assert summary.from_name == "noreply"


def test_parse_message_sans_objet():
    msg = _fixture(subject="")
    summary = _parse_graph_message(msg)
    assert summary.subject == "(Sans objet)"


def test_parse_message_sans_expediteur_retourne_none():
    msg = _fixture(**{"from": None})
    assert _parse_graph_message(msg) is None


def test_parse_datetime_avec_millisecondes():
    assert _parse_graph_datetime("2026-06-01T08:30:00.123Z") == _EXPECTED_EPOCH


def test_parse_datetime_sans_millisecondes():
    assert _parse_graph_datetime("2026-06-01T08:30:00Z") == _EXPECTED_EPOCH


def test_parse_datetime_vide():
    assert _parse_graph_datetime("") == 0


def test_parse_datetime_invalide():
    assert _parse_graph_datetime("pas une date") == 0
