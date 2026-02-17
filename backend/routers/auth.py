"""
MailScrub.app — Auth Router

Routes d'authentification OAuth 2.0 (stub pour le MVP).
Le vrai flux OAuth sera branché dans la Phase 2.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login():
    """
    Redirige vers Google OAuth pour l'authentification.
    MVP : retourne un message de statut.
    """
    return {
        "status": "demo_mode",
        "message": "OAuth sera intégré en Phase 2. Le dashboard fonctionne avec des données de démonstration.",
    }


@router.get("/callback")
async def callback(code: str = ""):
    """Callback OAuth — reçoit le token de Google."""
    return {
        "status": "demo_mode",
        "message": "Token reçu (simulation).",
    }


@router.get("/status")
async def auth_status():
    """Vérifie si l'utilisateur est connecté."""
    return {
        "authenticated": True,
        "mode": "demo",
        "user": {
            "email": "demo@mailscrub.app",
            "name": "Utilisateur Démo",
        },
    }
