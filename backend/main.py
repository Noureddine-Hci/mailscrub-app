"""
MailScrub.app — FastAPI Application

Point d'entrée de l'API backend.
Sert aussi les fichiers statiques du frontend.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

import os

# Load .env from the backend/ directory
load_dotenv(Path(__file__).resolve().parent / ".env")

from backend.routers import auth, analysis

# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="MailScrub.app",
    description="Diagnostic de santé pour votre boîte mail",
    version="0.2.0",
)

# ── Session Middleware (needed for OAuth) ─────────────────────

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "dev-secret-key"),
)

# ── CORS ──────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
