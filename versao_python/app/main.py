"""FastAPI main application for Judicial Case Summary generator.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Resumo para Audiência - TJRN / PJe",
    description="Aplicação automatizada e interativa para síntese de autos do PJe e confecção de minutas em DOCX para audiências judiciais.",
    version="1.0.0",
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_router)

# Mount static files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    """Serves the main SPA index.html."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "message": "API operacional. Frontend em inicialização.",
        "docs": "/docs",
    }
