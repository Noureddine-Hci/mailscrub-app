"""
Tests du parsing de la réponse POP3 TOP -> MessageSummary (logique pure,
sans connexion réseau).
"""

from backend.src.providers.base import MessageSummary
from backend.src.providers.pop_provider import _parse_top_response


def _top_lines(*lines: str) -> list[bytes]:
    return [line.encode() for line in lines]


def test_parse_simple_message():
    lines = _top_lines(
        "From: Marie Dupont <marie.dupont@gmail.com>",
        "Subject: Coucou",
        "Date: Mon, 01 Jun 2026 08:30:00 +0000",
    )
    summary = _parse_top_response("uid-101", lines)

    assert isinstance(summary, MessageSummary)
    assert summary.id == "uid-101"
    assert summary.from_addr == "marie.dupont@gmail.com"
    assert summary.from_name == "Marie Dupont"
    assert summary.subject == "Coucou"
    assert summary.date > 0
    assert summary.size_bytes == 0  # renseigné séparément via LIST, voir scan()


def test_parse_avec_list_unsubscribe():
    lines = _top_lines(
        "From: newsletter@medium.com",
        "Subject: Votre digest",
        "List-Unsubscribe: <https://medium.com/unsub>",
    )
    summary = _parse_top_response("uid-102", lines)
    assert summary.list_unsubscribe == "<https://medium.com/unsub>"


def test_parse_sans_expediteur_retourne_none():
    lines = _top_lines("Subject: Pas d'expéditeur")
    assert _parse_top_response("uid-103", lines) is None


def test_parse_sans_objet():
    lines = _top_lines("From: a@b.com")
    summary = _parse_top_response("uid-104", lines)
    assert summary.subject == "(Sans objet)"


def test_parse_sans_date():
    lines = _top_lines("From: a@b.com", "Subject: Test")
    summary = _parse_top_response("uid-105", lines)
    assert summary.date == 0
