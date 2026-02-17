"""
MailScrub.app — FastAPI Application

Point d'entrée de l'API backend.
Sert aussi les fichiers statiques du frontend.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers import auth, analysis

# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="MailScrub.app",
    description="Diagnostic de santé pour votre boîte mail",
    version="0.1.0",
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
