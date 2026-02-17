"""
MailScrub.app — Analysis Router

Route principale qui lance l'analyse et retourne les résultats
au dashboard (score, catégories, top expéditeurs, recommandations).
"""

from dataclasses import asdict

from fastapi import APIRouter

from backend.src.services.analyzer import MailAnalyzer

router = APIRouter(prefix="/api", tags=["analysis"])

analyzer = MailAnalyzer()


@router.get("/analyze")
async def analyze_mailbox():
    """
    Lance l'analyse de la boîte mail.

    MVP : utilise des données de démonstration.
    Production : utilisera le GmailConnector avec le token OAuth.
    """
    result = analyzer.analyze_demo()
    return asdict(result)
