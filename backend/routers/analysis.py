"""
MailScrub.app — Analysis Router

Route principale qui lance l'analyse et retourne les résultats
au dashboard (score, catégories, top expéditeurs, recommandations).

Utilise les vraies données Gmail si l'utilisateur est authentifié,
sinon retourne les données de démonstration.
"""

import traceback
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.src.services.analyzer import MailAnalyzer

router = APIRouter(prefix="/api", tags=["analysis"])

analyzer = MailAnalyzer()


@router.get("/analyze")
async def analyze_mailbox(request: Request):
    """
    Lance l'analyse de la boîte mail.

    Si l'utilisateur est connecté via OAuth, utilise les vraies données Gmail.
    Sinon, retourne les données de démonstration.
    """
    creds_data = request.session.get("credentials")

    if creds_data:
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            # Build real Gmail credentials from session
            credentials = Credentials(
                token=creds_data["token"],
                refresh_token=creds_data.get("refresh_token"),
                token_uri=creds_data["token_uri"],
                client_id=creds_data["client_id"],
                client_secret=creds_data["client_secret"],
                scopes=creds_data["scopes"],
            )

            # Build Gmail API service
            service = build("gmail", "v1", credentials=credentials)

            # Analyze real emails
            result = analyzer.analyze_real(service)
            data = asdict(result)
            data["mode"] = "gmail"
            return data

        except Exception as e:
            # Log the full error for debugging
            print(f"[ERROR] Gmail API failed: {e}")
            traceback.print_exc()

            # Return a clear error with fallback suggestion
            return JSONResponse(
                status_code=500,
                content={
                    "error": True,
                    "message": f"Erreur API Gmail: {str(e)}",
                    "fallback": "demo",
                },
            )
    else:
        # Fallback to demo data
        result = analyzer.analyze_demo()
        data = asdict(result)
        data["mode"] = "demo"
        return data
