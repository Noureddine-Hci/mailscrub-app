"""
Tests de la catégorisation des expéditeurs (logique pure, sans API Gmail).
"""

from backend.src.services.analyzer import _categorize_sender


def test_human_par_defaut():
    assert _categorize_sender("marie.dupont@gmail.com", "Marie Dupont", "Coucou") == "human"


def test_newsletter_par_mot_cle():
    assert _categorize_sender(
        "newsletter@medium.com", "Medium Daily Digest", "Votre digest"
    ) == "newsletter"


def test_notification_par_mot_cle():
    assert _categorize_sender(
        "support@stripe.com", "Stripe", "Reçu de paiement"
    ) == "notification"


def test_spam_exige_deux_signaux():
    # Un seul signal ne suffit pas (seuil = 2).
    assert _categorize_sender("contact@shop.com", "Shop", "Notre actualité") != "spam"
    # Plusieurs signaux forts -> spam.
    assert _categorize_sender(
        "win@promo.xyz", "You won a prize", "Claim your prize now"
    ) == "spam"


def test_regression_free_fr_pas_spam():
    # free.fr (FAI français) ne doit plus être catalogué spam.
    assert _categorize_sender("jean@free.fr", "Jean", "Salut") == "human"
