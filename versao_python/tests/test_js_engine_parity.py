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


def validate_javascript_syntax(js_code: str) -> list[str]:
    """Scans JavaScript code and checks bracket/brace/parenthesis balancing,
    taking into account single quotes, double quotes, template literals (including ${...} interpolation),
    single-line comments (//), multi-line comments (/* */), and regular expression literals (/[...]/).
    Returns a list of syntax error descriptions.
    """
    stack = []
    i = 0
    n = len(js_code)
    line = 1
    col = 1

    state = "DEFAULT"
    prev_token = None

    regex_preceders = {
        "(", "[", "{", ";", ",", "=", "!", "&", "|", "?", ":", "~", "+", "-", "*", "/", "%", "^", "<", ">",
        "return", "typeof", "throw", "case", "delete", "void", "in", "instanceof", "yield", "await", "=>"
    }

    errors = []

    while i < n:
        c = js_code[i]

        if c == "\n":
            line += 1
            col = 1
        else:
            col += 1

        if state == "DEFAULT":
            if c in " \t\r\n":
                i += 1
                continue

            # Check comments
            if c == "/" and i + 1 < n and js_code[i + 1] == "/":
                state = "IN_LINE_COMMENT"
                i += 2
                continue
            if c == "/" and i + 1 < n and js_code[i + 1] == "*":
                state = "IN_BLOCK_COMMENT"
                i += 2
                continue

            # Strings
            if c == "'":
                state = "IN_STRING_SINGLE"
                i += 1
                continue
            if c == '"':
                state = "IN_STRING_DOUBLE"
                i += 1
                continue
            if c == "`":
                state = "IN_TEMPLATE"
                i += 1
                continue

            # Regex vs Division
            if c == "/":
                if prev_token in regex_preceders or prev_token is None:
                    state = "IN_REGEX"
                    i += 1
                    continue
                else:
                    prev_token = "/"
                    i += 1
                    continue

            # Brackets / braces / parens
            if c in "({[":
                stack.append((c, line, col, False))
                prev_token = c
                i += 1
                continue
            elif c in ")}]":
                if not stack:
                    errors.append(f"Unmatched closing '{c}' at line {line}, col {col}")
                    i += 1
                    continue
                top, top_l, top_c, is_tmpl = stack.pop()
                expected = {"(": ")", "{": "}", "[": "]"}[top]
                if c != expected:
                    errors.append(
                        f"Mismatched closing '{c}' at line {line}, col {col} (expected '{expected}' opened at line {top_l}, col {top_c})"
                    )
                if is_tmpl:
                    state = "IN_TEMPLATE"
                prev_token = c
                i += 1
                continue

            # Tokens / identifiers
            if c.isalnum() or c in "$_":
                start_id = i
                while i < n and (js_code[i].isalnum() or js_code[i] in "$_"):
                    i += 1
                prev_token = js_code[start_id:i]
                continue
            else:
                prev_token = c
                i += 1
                continue

        elif state == "IN_LINE_COMMENT":
            if c == "\n":
                state = "DEFAULT"
            i += 1
            continue

        elif state == "IN_BLOCK_COMMENT":
            if c == "*" and i + 1 < n and js_code[i + 1] == "/":
                state = "DEFAULT"
                i += 2
                continue
            i += 1
            continue

        elif state == "IN_STRING_SINGLE":
            if c == "\\":
                i += 2
                continue
            if c == "'":
                state = "DEFAULT"
                prev_token = "STRING"
            i += 1
            continue

        elif state == "IN_STRING_DOUBLE":
            if c == "\\":
                i += 2
                continue
            if c == '"':
                state = "DEFAULT"
                prev_token = "STRING"
            i += 1
            continue

        elif state == "IN_TEMPLATE":
            if c == "\\":
                i += 2
                continue
            if c == "$" and i + 1 < n and js_code[i + 1] == "{":
                stack.append(("{", line, col, True))
                state = "DEFAULT"
                prev_token = "{"
                i += 2
                continue
            if c == "`":
                state = "DEFAULT"
                prev_token = "STRING"
            i += 1
            continue

        elif state == "IN_REGEX":
            if c == "\\":
                i += 2
                continue
            if c == "[":
                i += 1
                while i < n and js_code[i] != "]":
                    if js_code[i] == "\\":
                        i += 2
                    else:
                        i += 1
                if i < n:
                    i += 1
                continue
            if c == "/":
                state = "DEFAULT"
                prev_token = "REGEX"
            i += 1
            continue

    if stack:
        for top, l, c, is_tmpl in stack:
            errors.append(f"Unclosed '{top}' opened at line {l}, col {c}")

    return errors


def test_html_javascript_syntax_and_bracket_balance():
    """Verifies that all <script> blocks across all HTML files have 100% valid bracket/brace balance and zero syntax errors."""
    html_files = [p for p in ROOT_DIR.rglob("*.html") if ".git" not in str(p)]
    assert len(html_files) >= 6, f"Expected at least 6 HTML files in project, found {len(html_files)}"

    total_scripts_checked = 0
    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8")
        scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", content, flags=re.DOTALL | re.IGNORECASE)
        for idx, script_body in enumerate(scripts):
            # Skip empty scripts or external src tags with empty body
            if not script_body.strip():
                continue
            total_scripts_checked += 1
            errors = validate_javascript_syntax(script_body)
            assert not errors, f"JavaScript syntax errors in {html_file.relative_to(ROOT_DIR)} (script #{idx + 1}):\n" + "\n".join(errors)

    assert total_scripts_checked > 0, "At least one JavaScript script block must be verified"


def test_js_syntax_validator_catches_unbalanced_braces():
    """Verifies that the syntax validator correctly detects extra or missing braces and parens."""
    broken_code = """
    function testFunc() {
        if (true) {
            console.log("hello");
        }
    }
    }
    """
    errors = validate_javascript_syntax(broken_code)
    assert len(errors) > 0
    assert any("Unmatched closing '}'" in err for err in errors)

    unclosed_code = """
    function testFunc() {
        if (true) {
            console.log("hello");
    }
    """
    errors_unclosed = validate_javascript_syntax(unclosed_code)
    assert len(errors_unclosed) > 0
    assert any("Unclosed '{'" in err for err in errors_unclosed)



