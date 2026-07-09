"""
Tests du parsing de la réponse IMAP FETCH -> MessageSummary (logique pure,
sans connexion réseau). Fixture imitant la forme réelle renvoyée par imaplib
(liste de tuples (meta, headers) entrecoupée d'octets de clôture type b")").
"""

from backend.src.providers.base import MessageSummary
from backend.src.providers.imap_provider import _parse_fetch_response


def _fetch_item(uid: int, size: int, headers: str) -> tuple:
    meta = (
        f"1 (UID {uid} RFC822.SIZE {size} "
        f"BODY[HEADER.FIELDS (FROM SUBJECT LIST-UNSUBSCRIBE DATE)] {{{len(headers)}}}"
    ).encode()
    return (meta, headers.encode())


def test_parse_simple_message():
    headers = (
        "From: Marie Dupont <marie.dupont@gmail.com>\r\n"
        "Subject: Coucou\r\n"
        "Date: Mon, 01 Jun 2026 08:30:00 +0000\r\n\r\n"
    )
    msg_data = [_fetch_item(101, 2048, headers), b")"]

    summaries = _parse_fetch_response(msg_data)

    assert len(summaries) == 1
    s = summaries[0]
    assert isinstance(s, MessageSummary)
    assert s.id == "101"
    assert s.from_addr == "marie.dupont@gmail.com"
    assert s.from_name == "Marie Dupont"
    assert s.subject == "Coucou"
    assert s.size_bytes == 2048
    assert s.list_unsubscribe == ""
    assert s.date > 0


def test_parse_avec_list_unsubscribe():
    headers = (
        "From: Medium Daily Digest <newsletter@medium.com>\r\n"
        "Subject: Votre digest\r\n"
        "List-Unsubscribe: <https://medium.com/unsub>\r\n\r\n"
    )
    msg_data = [_fetch_item(102, 4096, headers), b")"]

    summaries = _parse_fetch_response(msg_data)

    assert summaries[0].list_unsubscribe == "<https://medium.com/unsub>"


def test_parse_plusieurs_messages():
    headers1 = "From: a@example.com\r\nSubject: Un\r\n\r\n"
    headers2 = "From: b@example.com\r\nSubject: Deux\r\n\r\n"
    msg_data = [_fetch_item(1, 100, headers1), b")", _fetch_item(2, 200, headers2), b")"]

    summaries = _parse_fetch_response(msg_data)

    assert len(summaries) == 2
    assert {s.id for s in summaries} == {"1", "2"}


def test_parse_ignore_entree_sans_uid():
    # Entrée malformée sans "UID xxx" dans la partie meta -> ignorée, pas de crash.
    msg_data = [(b"1 (BODYSTRUCTURE ...)", b"From: a@b.com\r\n\r\n"), b")"]
    assert _parse_fetch_response(msg_data) == []


def test_parse_sans_expediteur_ignore():
    headers = "Subject: Pas d'expéditeur\r\n\r\n"
    msg_data = [_fetch_item(3, 100, headers)]
    assert _parse_fetch_response(msg_data) == []


def test_parse_sans_objet():
    headers = "From: a@b.com\r\n\r\n"
    msg_data = [_fetch_item(4, 100, headers)]
    summaries = _parse_fetch_response(msg_data)
    assert summaries[0].subject == "(Sans objet)"
