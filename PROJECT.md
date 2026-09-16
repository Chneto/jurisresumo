# Project: Automated Judicial Case Summary Application (Resumo para Audiência PJe / TJRN)

## Architecture
- **Host / Platform:** Windows 10/11 x64, Python 3.13.15.
- **Backend Architecture:** Modular Python backend using FastAPI, PyMuPDF (fitz), python-docx, pydantic, rapidocr-onnxruntime, and google-genai.
- **Frontend Architecture:** Zero-build modern SPA (HTML5 / Vanilla ES6 / CSS3 custom properties) adopting Google Stitch & Nano Banana visual aesthetics (high contrast cards, refined palette, clean typography, responsive layout), served directly by FastAPI static files.
- **Data Flow:**
  1. User drops a PJe PDF file into the web UI.
  2. PDF is streamed to backend (`/api/upload`).
  3. `PJeDocumentIndexer` parses the initial Table of Documents (pages 1..N) and footer stamps (`Num. <ID> - Pág. <P>`), building an index of all legal acts and isolating key documents (Denúncia, Decisões, Resposta à Acusação, Mandados/Certidões de Intimação).
  4. User selects Engine:
     - **Mode 1 (Gemini AI):** Formats targeted text snippets of key documents into prompt with few-shot schema, calls Google Gemini API (via `google-genai`), and parses validated JSON.
     - **Mode 2 (100% Offline Local):** Pure local regex patterns and rule-based heuristics extract structured fields with zero network requests. Scanned pages are selectively OCR-processed locally via `rapidocr-onnxruntime`.
  5. Extracted data is returned as structured JSON to the web UI.
  6. User interactively reviews, edits, adds, or removes fields in the UI cards with real-time preview.
  7. User clicks "Baixar Resumo (.docx)" -> sends edited JSON to `/api/generate-docx` -> `DOCXGenerator` builds the Word document conforming to verified reference OpenXML specs and returns it as a download stream.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F01 | Dual Engine Toggle | UI toggle between Gemini AI (Mode 1) and 100% Offline Local (Mode 2) with API key configuration | M4 | ORIGINAL_REQUEST §R1, §R3 |
| F02 | Gemini AI Extraction (Mode 1) | PyMuPDF selective extraction + Gemini AI structured JSON output conforming to judicial schema | M2 | ORIGINAL_REQUEST §R1 |
| F03 | 100% Offline Local Engine (Mode 2) | Local regex and heuristic parsing of PJe documents with zero external network calls | M2 | ORIGINAL_REQUEST §R1 |
| F04 | Offline OCR Integration | Selective local OCR (`rapidocr-onnxruntime`) on scanned pages without vector text | M1 | ORIGINAL_REQUEST §R1 |
| F05 | PJe Index & Stamp Parsing | Parse PJe Table of Documents and footer stamps (`Num. <ID> - Pág. <P>`) to catalog and prune pages | M1 | ORIGINAL_REQUEST §R2 |
| F06 | Cabeçalho Section Extraction | Extract Processo, ato, data/hora, link videoconferência/presencial, Promotor, Réus com situação/intimação, Defesa | M2 | ORIGINAL_REQUEST §R2 |
| F07 | Qualificação Section Extraction | Extract Nome em caixa alta, RG, CPF, filiação, endereço, telefone, idade | M2 | ORIGINAL_REQUEST §R2 |
| F08 | Imputação Section Extraction | Extract penal articles, laws, paragraphs, and incident clauses | M2 | ORIGINAL_REQUEST §R2 |
| F09 | Resumo dos Fatos Extraction | Extract/transcribe complaint facts, police interrogation/confession, forensic reports, and IDs | M2 | ORIGINAL_REQUEST §R2 |
| F10 | Histórico Processual Extraction | Chronological strict timeline: `DD/MM/AA: [Descrição] (ID [número])` with valid PJe IDs | M2 | ORIGINAL_REQUEST §R2 |
| F11 | Rol de Testemunhas Extraction | Witness lists (Acusação and Defesa) with subpoena IDs and qualification | M2 | ORIGINAL_REQUEST §R2 |
| F12 | Formal Closure Section | Exact formal closure `Cordial e respeitosamente,` | M3 | ORIGINAL_REQUEST §R2 |
| F13 | Special Case Formats | Support ANPP (agreement conditions, OBS block) and PAnP (art. 366 CPP) formats | M2, M3 | Survey discovery |
| F14 | Modern Web UI | Google Stitch & Nano Banana aesthetic, high contrast cards, refined palette, clear loading states | M4 | ORIGINAL_REQUEST §R3 |
| F15 | Drag-and-Drop PDF Upload | Drag-and-drop zone supporting complete PJe case PDFs up to hundreds of megabytes | M4 | ORIGINAL_REQUEST §R3 |
| F16 | Interactive Field Editor | Full UI editing, addition, deletion of all extracted fields prior to export | M4 | ORIGINAL_REQUEST §R3 |
| F17 | Real-Time Summary Preview | Formatted preview closely simulating DOCX output in browser | M4 | ORIGINAL_REQUEST §R3 |
| F18 | High-Fidelity DOCX Generator | Generate `.docx` matching reference models: A4 portrait, 2cm margins, Verdana 12pt, ~1.9x spacing, exact bolding and PJe hyperlinks | M3 | ORIGINAL_REQUEST §R4 |
| F19 | 1-Click DOCX Download | Instant download button generating and serving `.docx` from UI state | M4 | ORIGINAL_REQUEST §R3 |
| F20 | Automated E2E Test Suite | Test suite verifying field extraction, chronological history, IDs, and DOCX generation across the 9 cases | M5 | ORIGINAL_REQUEST §R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | PJe Ingestion & Indexer | PJe index table parser, footer stamp matcher, selective page pruner, offline OCR module, core Pydantic models | None | IN_PROGRESS (worker: 9d527e2e-b03b-4846-934f-3b6a9e6f77b9) |
| M2 | Dual Extraction Engines | Mode 1 (Gemini AI) + Mode 2 (100% Offline Local Engine) extracting all 6 judicial sections + ANPP/PAnP | M1 | PLANNED |
| M3 | High-Fidelity DOCX Generator | `python-docx` builder adhering to exact OpenXML specs (Verdana 12pt, margins, bolding rules, PJe links) | M1 | PLANNED |
| M4 | Modern Web UI & API | FastAPI backend endpoints + Stitch/Nano Banana responsive frontend (upload, edit, preview, download) | M2, M3 | PLANNED |
| M5 | System Integration & E2E Validation | Phase 1: 100% E2E test pass across the 9 cases; Phase 2: Adversarial coverage hardening | M4, E2E | PLANNED |

## Interface Contracts

### `app.core.models` (Canonical Data Schema)
```python
class Defendant(BaseModel):
    name: str
    status: str  # e.g., "solto", "preso provisoriamente"
    citation_id: Optional[str] = None
    subpoena_id: Optional[str] = None
    qualification: Optional[str] = None

class Witness(BaseModel):
    number: int
    name: str
    role: str  # e.g., "Vítima", "Policial Militar", "Testemunha Presencial"
    status_id: Optional[str] = None

class HistoryItem(BaseModel):
    date_str: str  # DD/MM/AA
    description: str
    doc_id: str
    pje_url: Optional[str] = None

class HearingSummaryData(BaseModel):
    case_number: str
    act_type: str  # AIJ, ANPP, PAnP
    hearing_datetime: str
    hearing_link: Optional[str] = None
    is_in_person: bool = False
    prosecutor: str
    defendants: List[Defendant]
    defense_counsel: str
    qualification_text: Optional[str] = None
    imputation_text: Optional[str] = None
    facts_summary: Optional[str] = None
    chronological_history: List[HistoryItem]
    prosecution_witnesses: List[Witness]
    defense_witnesses: List[Witness]
    defense_witness_note: Optional[str] = None
    special_notes: Optional[str] = None  # for ANPP conditions or PAnP
    closure_text: str = "Cordial e respeitosamente,"
```

### `app.core.pje_indexer` ↔ Engines
```python
class PJeDocument(BaseModel):
    doc_id: str
    date_str: str
    doc_name: str
    doc_type: str
    start_page: int  # 1-indexed
    end_page: int
    is_scanned: bool = False

def index_pje_pdf(pdf_path: str) -> Tuple[List[PJeDocument], fitz.Document]:
    """Parses index table and footer stamps; returns document catalog and open PyMuPDF Doc."""
```

### Engines ↔ Web API
```python
def extract_summary(
    pdf_path: str,
    engine_mode: str,  # "gemini" | "offline"
    api_key: Optional[str] = None,
    pje_catalog: Optional[List[PJeDocument]] = None
) -> HearingSummaryData:
    """Extracts complete structured hearing summary data."""
```

### `app.generators.docx_generator` ↔ Web API
```python
def generate_docx_summary(data: HearingSummaryData, output_path: Optional[str] = None) -> bytes:
    """Generates byte-perfect DOCX matching reference specs and returns bytes or writes to file."""
```

## Code Layout
```
c:\Users\f201503\Documents\Resumo para audiência\
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py               # Pydantic models for hearing summaries
│   │   ├── pje_indexer.py          # Table of Documents & footer stamp parser
│   │   └── ocr_engine.py           # RapidOCR local wrapper for scanned pages
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract base extraction engine
│   │   ├── offline_engine.py       # 100% Offline regex & heuristics engine
│   │   └── gemini_engine.py        # Gemini AI structured extraction engine
│   ├── generators/
│   │   ├── __init__.py
│   │   └── docx_generator.py       # High-fidelity OpenXML/DOCX builder
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py               # API routes (/upload, /extract, /generate-docx)
│   └── static/
│       ├── index.html              # Modern Web UI (Google Stitch & Nano Banana)
│       ├── css/
│       │   └── style.css           # High-contrast, refined palette design
│       └── js/
│           └── app.js              # Interactive state management, preview, export
├── tests/
│   ├── __init__.py
│   ├── test_pje_indexer.py         # Unit tests for PJe indexer across 9 cases
│   ├── test_offline_engine.py      # Unit tests for Mode 2 extraction
│   ├── test_docx_generator.py      # Unit tests for DOCX formatting and specs
│   ├── test_api.py                 # API integration tests
│   └── e2e/
│       ├── test_e2e_tier1_features.py
│       ├── test_e2e_tier2_boundaries.py
│       ├── test_e2e_tier3_cross_features.py
│       └── test_e2e_tier4_workloads.py
├── run.py                          # Local CLI / server launcher
├── requirements.txt
├── PROJECT.md
├── TEST_INFRA.md
└── TEST_READY.md                   # Created when E2E test track is complete
```
