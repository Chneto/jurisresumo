"""FastAPI main application for Judicial Case Summary generator.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

from pathlib import Path
from fastapi import FastAPI, HTTPException
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

# Register API routes first so they take precedence
app.include_router(api_router)

# Mount static files
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Mount dedicated subdirectories for direct relative asset resolution (e.g. css/style.css, js/app.js)
css_dir = STATIC_DIR / "css"
if css_dir.exists():
    app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")

js_dir = STATIC_DIR / "js"
if js_dir.exists():
    app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")

vendor_dir = STATIC_DIR / "vendor"
if vendor_dir.exists():
    app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")

# Mount /static for explicit /static/... asset requests
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
@app.get("/index.html")
def serve_index():
    """Serves the main SPA index.html."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "message": "API operacional. Frontend em inicialização.",
        "docs": "/docs",
    }


@app.get("/{file_name:path}")
def serve_static_root(file_name: str):
    """Fallback route to serve static assets located in STATIC_DIR."""
    target = (STATIC_DIR / file_name).resolve()
    if target.is_file() and target.is_relative_to(STATIC_DIR):
        return FileResponse(target)
    raise HTTPException(status_code=404, detail="Recurso não encontrado.")

