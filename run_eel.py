"""JURISRESUMO - Desktop Launcher powered by Eel & Microsoft Edge.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import base64
import json
import os
import sys
import tempfile
from pathlib import Path

import eel
import eel.browsers

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "app" / "static"
if not str(BASE_DIR) in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure root sample directory is findable if needed
ROOT_DIR = BASE_DIR.parent if (BASE_DIR.parent / "Proc. 0801889-53.2023.8.20.5001").exists() else BASE_DIR

from app.core.models import HearingSummaryData
from app.engines import get_engine
from app.generators.docx_generator import generate_docx_summary


def setup_browser():
    """Detects Edge or Chrome and configures Eel browser paths."""
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]

    for p in edge_paths:
        if os.path.isfile(p):
            eel.browsers.set_path("edge", p)
            return "edge"

    for p in chrome_paths:
        if os.path.isfile(p):
            eel.browsers.set_path("chrome", p)
            return "chrome"

    return "default"


@eel.expose
def process_pdf_eel(base64_data: str, filename: str, engine_mode: str = "offline", api_key: str = None):
    """Processes uploaded PDF autos directly in Python without HTTP overhead."""
    temp_dir = Path(tempfile.gettempdir()) / "pje_resumos_eel"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_pdf = temp_dir / filename

    try:
        pdf_bytes = base64.b64decode(base64_data)
        temp_pdf.write_bytes(pdf_bytes)

        engine = get_engine(mode=engine_mode, api_key=api_key)
        data = engine.extract(str(temp_pdf), api_key=api_key)
        return {"data": data.model_dump()}
    except Exception as exc:
        return {"error": f"Erro na extração dos autos: {str(exc)}"}
    finally:
        if temp_pdf.exists():
            try:
                temp_pdf.unlink()
            except OSError:
                pass


@eel.expose
def generate_docx_eel(summary_json: str) -> str:
    """Generates DOCX summary and returns base64 encoded bytes."""
    try:
        data_dict = json.loads(summary_json)
        data = HearingSummaryData(**data_dict)
        docx_bytes = generate_docx_summary(data)
        return base64.b64encode(docx_bytes).decode("utf-8")
    except Exception as exc:
        return f"ERROR: {str(exc)}"


def launch():
    """Initializes and runs the Eel desktop application."""
    print("=" * 75)
    print("  JURISRESUMO - Desktop App (Eel + Edge/Chrome)")
    print("  Desenvolvido por FChNeto")
    print("=" * 75)

    eel.init(str(STATIC_DIR))
    browser = setup_browser()
    print(f"  [INFO] Navegador selecionado para janela nativa: {browser}")

    try:
        eel.start(
            "index.html",
            mode=browser,
            size=(1440, 920),
            port=0,  # Auto-assign available port
            cmdline_args=["--disable-features=Translate", "--no-first-run"],
        )
    except Exception as exc:
        print(f"  [AVISO] Não foi possível iniciar em modo {browser}: {exc}")
        print("  [INFO] Tentando modo navegador padrão do sistema...")
        eel.start("index.html", mode="default", port=0)


if __name__ == "__main__":
    launch()
