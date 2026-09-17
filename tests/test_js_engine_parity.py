"""Automated test suite verifying the JavaScript portable version and structural parity.
Tests physical folder separation, presence of vendor libraries, key analytical engine functions,
DOCX OpenXML styling adherence, and author metadata.
Autor: FChNeto
"""

import os
import re
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if not any(PROJECT_ROOT.glob("Proc.*")) and any(PROJECT_ROOT.parent.glob("Proc.*")):
    PROJECT_ROOT = PROJECT_ROOT.parent

JS_DIR = PROJECT_ROOT / "versao_javascript"
PY_DIR = PROJECT_ROOT / "versao_python"
ROOT_DIR = PROJECT_ROOT


def test_directory_separation_exists():
    """Verifies that dedicated folders for Python and JavaScript versions exist."""
    assert JS_DIR.is_dir(), f"Folder {JS_DIR} must exist"
    assert PY_DIR.is_dir(), f"Folder {PY_DIR} must exist"


def test_root_launchers_exist():
    """Verifies that clear, dedicated launchers exist at workspace root."""
    py_vbs = ROOT_DIR / "ABRIR_VERSAO_PYTHON.vbs"
    js_html = ROOT_DIR / "ABRIR_VERSAO_JAVASCRIPT.html"
    assert py_vbs.is_file(), "ABRIR_VERSAO_PYTHON.vbs must exist in root"
    assert js_html.is_file(), "ABRIR_VERSAO_JAVASCRIPT.html must exist in root"

    vbs_content = py_vbs.read_text(encoding="latin1")
    assert "versao_python" in vbs_content
    assert "FChNeto" in vbs_content

    html_content = js_html.read_text(encoding="utf-8")
    assert "versao_javascript/index.html" in html_content
    assert "FChNeto" in html_content


def test_python_version_self_contained():
    """Verifies that versao_python contains all necessary autonomous backend components."""
    assert (PY_DIR / "run.py").is_file()
    assert (PY_DIR / "Iniciar_JURISRESUMO.vbs").is_file()
    assert (PY_DIR / "requirements.txt").is_file()
    assert (PY_DIR / "app" / "main.py").is_file()
    assert (PY_DIR / "app" / "api" / "routes.py").is_file()
    assert (PY_DIR / "app" / "core" / "pje_indexer.py").is_file()
    assert (PY_DIR / "app" / "engines" / "offline_engine.py").is_file()
    assert (PY_DIR / "app" / "generators" / "docx_generator.py").is_file()
    assert (PY_DIR / "app" / "static" / "index.html").is_file()
    assert (PY_DIR / "tests").is_dir()


def test_javascript_version_self_contained():
    """Verifies that versao_javascript contains standalone vendor libraries and HTML files."""
    assert (JS_DIR / "index.html").is_file()
    assert (JS_DIR / "ABRIR_APLICATIVO_DIRETO.html").is_file()
    assert (JS_DIR / "vendor" / "pdf.min.js").is_file()
    assert (JS_DIR / "vendor" / "pdf.worker.min.js").is_file()
    assert (JS_DIR / "vendor" / "jszip.min.js").is_file()


def test_javascript_analytical_engine_features():
    """Verifies that the JavaScript application contains the deep analytical engine features."""
    index_file = JS_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Author metadata
    assert 'meta name="author" content="FChNeto"' in content
    assert "FChNeto" in content

    # Key analytical functions
    assert "analyzePjeRecords" in content
    assert "summarizeHistoryAct" in content
    assert "parsePtDateTime" in content
    assert "extractCleanNarrative" in content
    assert "findSubpoenaStatus" in content

    # TOC and footer stamp detection
    assert "stampDocId" in content
    assert "pjeCatalog" in content
    assert "Num" in content

    # Procedural act classification & negation check
    assert "anppNegationRegex" in content
    assert "hearingDesigRegex" in content

    # ANPP 6 reference analytical paragraphs
    assert "CONDIÇÕES DO ACORDO:" in content or "CONDI\\u00c7\\u00d5ES DO ACORDO:" in content or "CONDI" in content
    assert "desmembramento da ação penal" in content

    # OpenXML DOCX builder with strict styling
    assert 'highlight: "green"' in content
    assert 'highlight: "yellow"' in content
    assert '<w:highlight w:val="${highlight}"/>' in content
    assert 'w:color w:val="${color}"' in content or '0000ff' in content
    assert 'w:u w:val="single"' in content
    assert '{ left: 720, hanging: 360 }' in content
    assert 'w:ind w:left="${left}" w:hanging="${hanging}"' in content


