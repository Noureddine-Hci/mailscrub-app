"""
Tests du calcul du Mail Health Score (logique pure).
"""

from backend.src.services.analyzer import MailAnalyzer


def test_inbox_saine_score_eleve():
    a = MailAnalyzer()
    score, details = a._calculate_score(
        {"human": 80, "newsletter": 10, "notification": 10, "spam": 0}
    )
    assert score >= 90
    assert isinstance(details, list) and details


def test_spam_penalise_le_score():
    a = MailAnalyzer()
    clean, _ = a._calculate_score(
        {"human": 50, "newsletter": 20, "notification": 30, "spam": 0}
    )
    spammy, _ = a._calculate_score(
        {"human": 50, "newsletter": 20, "notification": 10, "spam": 20}
    )
    assert spammy < clean


def test_score_borne_0_100():
    a = MailAnalyzer()
    score, _ = a._calculate_score(
        {"human": 0, "newsletter": 0, "notification": 0, "spam": 100}
    )
    assert 0 <= score <= 100
