"""
MailScrub.app — FastAPI Application

Point d'entrée de l'API backend.
Sert aussi les fichiers statiques du frontend.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

# Load .env from the backend/ directory
load_dotenv(Path(__file__).resolve().parent / ".env")

from backend.routers import auth, analysis

# ── Environment ───────────────────────────────────────────────

IS_PROD = bool(os.getenv("K_SERVICE"))  # Cloud Run injecte K_SERVICE

# SECRET_KEY signe les cookies de session. En production, son absence est
# fatale : un fallback connu permettrait à quiconque de forger des sessions.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if IS_PROD:
        raise RuntimeError(
            "SECRET_KEY manquant en production. Définissez la variable "
            "d'environnement avant de démarrer le service."
        )
    SECRET_KEY = "dev-secret-key"  # local uniquement

# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="MailScrub.app",
    description="Diagnostic de santé pour votre boîte mail",
    version="0.2.0",
)

# ── Session Middleware (needed for OAuth) ─────────────────────
# Le cookie de session est SIGNÉ mais pas chiffré : on n'y stocke donc aucun
# secret applicatif (voir routers/auth.py). `https_only` ajoute le flag Secure
# en prod ; `same_site="lax"` protège du CSRF tout en laissant passer le retour
# de navigation OAuth (un "strict" casserait le callback Google).

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=IS_PROD,
    same_site="lax",
)

# ── CORS ──────────────────────────────────────────────────────
# Le frontend est servi par cette même application (même origine) : aucune
# configuration CORS n'est nécessaire. On évite volontairement une politique
# permissive (`*` + credentials) qui serait exploitable.

# ── Routers ───────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(analysis.router)

# ── Static Files (Frontend) ──────────────────────────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
async def serve_frontend():
    """Sert la page principale du dashboard."""
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/privacy.html")
async def serve_privacy():
    """Sert la page de politique de confidentialité."""
    return FileResponse(FRONTEND_DIR / "privacy.html")

@app.get("/terms.html")
async def serve_terms():
    """Sert la page des conditions d'utilisation."""
    return FileResponse(FRONTEND_DIR / "terms.html")
