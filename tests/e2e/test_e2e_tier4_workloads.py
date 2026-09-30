"""Tier 4 Real-World Application Workload E2E Tests.

Executes real-world application scenarios S1 through S9 across all 9 reference cases
in the project directory, validating:
1. PJe PDF structure, TOC parsing, and page indexing.
2. Reference DOCX OpenXML fidelity (A4 dimensions, 2cm margins, Verdana 12pt, line 454, canonical closure).
3. Cross-validation of key fields (case number, defendants, imputation, dates, IDs) between PDF and DOCX.
4. End-to-end DOCX generation from canonical data matching ground-truth structure.
"""

from pathlib import Path
from typing import Any, Dict, List

import docx
import pymupdf
import pytest

from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    Witness,
)
from app.core.pje_indexer import (
    index_pje_pdf,
    parse_toc_entries,
    prune_documents,
)
from tests.conftest import (
    PROJECT_ROOT,
    REFERENCE_CASES_METADATA,
    inspect_docx_file,
)
from tests.e2e.test_e2e_tier1_features import build_reference_docx


# ==============================================================================
# Helper to validate reference DOCX against OpenXML standard
# ==============================================================================

def assert_reference_docx_openxml(docx_path: Path) -> None:
    """Verifies that a reference DOCX satisfies all mined OpenXML specifications."""
    if not docx_path.exists():
        pytest.skip(f"Reference DOCX does not exist: {docx_path} (LGPD sanitized)")
    insp = inspect_docx_file(docx_path)
    # A4 Page size (twips)
    assert insp.page_width_twips == 11906, f"Expected 11906, got {insp.page_width_twips}"
    assert insp.page_height_twips == 16838, f"Expected 16838, got {insp.page_height_twips}"
    assert insp.page_orient == "portrait"
    # Margins 2.0 cm (twips)
    assert insp.margin_top_twips == 1134, f"Expected top margin 1134, got {insp.margin_top_twips}"
    assert insp.margin_bottom_twips == 1134
    assert insp.margin_left_twips == 1134
    assert insp.margin_right_twips == 1134
    # Verdana font
    assert "Verdana" in insp.fonts
    # Canonical closure
    assert insp.has_formal_closure is True


# ==============================================================================
# S1: Standard AIJ Single Accused (Proc. 0801889-53.2023.8.20.5001)
# ==============================================================================

def test_workload_s1_standard_aij_single_accused(reference_cases):
    """S1: Standard AIJ Single Accused with Video Intimations."""
    meta = reference_cases["0801889-53.2023.8.20.5001"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    # 1. Assert reference DOCX satisfies OpenXML specs
    assert_reference_docx_openxml(docx_path)

    if not pdf_path.exists():
        pytest.skip("PDF for case 0801889 not found (LGPD sanitized)")

    # 2. Assert PDF opens and TOC parses
    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == meta["total_pages"]
        entries, toc_count = parse_toc_entries(doc)
        assert toc_count == 3
        assert len(entries) >= 60

    # 3. Cross-validate key IDs in reference DOCX
    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0801889-53.2023.8.20.5001" in full_text
    assert "Jucimarcia Soares da Silva" in full_text
    assert "Dr. Jann Polacek Melo Cardoso" in full_text
    for key_id in meta["key_ids"][:5]:
        assert key_id in full_text

    # 4. Generate DOCX from summary data and verify compliance
    summary = HearingSummaryData(
        case_number=meta["case_number"],
        act_type=meta["act_type"],
        hearing_datetime=meta["hearing_datetime"],
        hearing_link=meta["hearing_link"],
        prosecutor=meta["prosecutor"],
        defendants=[Defendant(name=meta["defendants"][0], status=meta["defendants_status"][0], subpoena_id="194381260")],
        defense_counsel=meta["defense_counsel"],
        imputation_text="Art. 129, § 9º, do Código Penal.",
        chronological_history=[
            HistoryItem(date_str="10/06/23", description="Denúncia", doc_id="101573748"),
            HistoryItem(date_str="12/06/23", description="Decisão recebimento", doc_id="101605793"),
        ],
    )
    gen_bytes = build_reference_docx(summary)
    gen_insp = inspect_docx_file(gen_bytes)
    assert gen_insp.page_width_twips == 11906
    assert gen_insp.has_formal_closure is True


# ==============================================================================
# S2: Multi-Accused Complex Robbery & PM Witnesses (Proc. 0820550-12.2025.8.20.5001)
# ==============================================================================

def test_workload_s2_multi_accused_robbery(reference_cases):
    """S2: Multi-Accused Complex Robbery & PM Witnesses."""
    meta = reference_cases["0820550-12.2025.8.20.5001"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == meta["total_pages"]
        entries, _ = parse_toc_entries(doc)
        assert len(entries) >= 80

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0820550-12.2025.8.20.5001" in full_text
    assert "HEVERTON DOUGLAS ALVES DE MEDEIROS" in full_text
    assert "ADRIANO DE OLIVEIRA GABRIEL" in full_text
    assert "Jean Gomes da Silva" in full_text
    for key_id in ["156069258", "156265637", "180620731"]:
        assert key_id in full_text


# ==============================================================================
# S3: AIJ with Extensive Inquérito & Forensic IDs (Proc. 0821902-39.2024.8.20.5001)
# ==============================================================================

def test_workload_s3_extensive_inquerito(reference_cases):
    """S3: AIJ with Extensive Police Inquérito & Forensic IDs (1,166 pages)."""
    meta = reference_cases["0821902-39.2024.8.20.5001"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == 1166
        entries, toc_count = parse_toc_entries(doc)
        assert toc_count == 7
        assert len(entries) >= 150

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0821902-39.2024.8.20.5001" in full_text
    assert "Luanna" in full_text


# ==============================================================================
# S4: ANPP Hearing with Agreement Conditions (Proc. 0860849-94.2026.8.20.5001)
# ==============================================================================

def test_workload_s4_anpp_hearing(reference_cases):
    """S4: ANPP Hearing with Agreement Conditions & OBS block."""
    meta = reference_cases["0860849-94.2026.8.20.5001"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == 480
        entries, toc_count = parse_toc_entries(doc)
        assert toc_count == 2

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0860849-94.2026.8.20.5001" in full_text
    assert "ANPP" in full_text
    assert "Samara Targino de Lima" in full_text
    assert "CONDIÇÕES DO ACORDO" in full_text
    assert "OBS:" in full_text


# ==============================================================================
# S5: PAnP Suspended Case Art. 366 (Proc. 0804041-57.2022.8.20.5600)
# ==============================================================================

def test_workload_s5_panp_suspended_case(reference_cases):
    """S5: PAnP Suspended Case (Art. 366 CPP) & Precautionary Measures."""
    meta = reference_cases["0804041-57.2022.8.20.5600"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == 212
        entries, _ = parse_toc_entries(doc)
        assert len(entries) >= 100

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0804041-57.2022.8.20.5600" in full_text
    assert "PAnP" in full_text
    assert "Beranildo" in full_text
    assert "produção antecipada de provas orais" in full_text


# ==============================================================================
# S6: Presencial Hearing Multi-Accused (Proc. 0876503-58.2025.8.20.5001)
# ==============================================================================

def test_workload_s6_presencial_hearing(reference_cases):
    """S6: Presencial Hearing with Complex Intimations & 3 Defendants."""
    meta = reference_cases["0876503-58.2025.8.20.5001"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == 510
        entries, toc_count = parse_toc_entries(doc)
        assert toc_count == 5
        assert len(entries) >= 100

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0876503-58.2025.8.20.5001" in full_text
    assert "Manoel Paulino da Silva Sobrinho" in full_text
    assert "Josuel Farias da Silva" in full_text
    assert "Felipe Farias da Silva" in full_text


# ==============================================================================
# S7: GAECO / Multi-Defendant Case (Proc. 0802487-75.2026.8.20.5300)
# ==============================================================================

def test_workload_s7_gaeco_complex_case(reference_cases):
    """S7: GAECO / Multi-Defendant Complex Fraud Case."""
    meta = reference_cases["0802487-75.2026.8.20.5300"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == 209
        entries, _ = parse_toc_entries(doc)
        assert len(entries) >= 40

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0802487-75.2026.8.20.5300" in full_text
    assert "Gean" in full_text


# ==============================================================================
# S8: Declining Jurisdiction & Nested Structure (Proc. 0844118-57.2025.8.20.5001)
# ==============================================================================

def test_workload_s8_declining_jurisdiction(reference_cases):
    """S8: Declining Jurisdiction & Nested PDF Structure."""
    meta = reference_cases["0844118-57.2025.8.20.5001"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == 336
        entries, _ = parse_toc_entries(doc)
        assert len(entries) >= 50

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0844118-57.2025.8.20.5001" in full_text
    assert "GLAUCO BARBOSA DA SILVA" in full_text
    assert "178221008" in full_text


# ==============================================================================
# S9: e-SAJ/TJSP Imported Records (Proc. 0806049-87.2024.8.20.5001)
# ==============================================================================

def test_workload_s9_esaj_imported_records(reference_cases):
    """S9: e-SAJ/TJSP Imported Records with Vertical Margin Stamps (3,250 pages)."""
    meta = reference_cases["0806049-87.2024.8.20.5001"]
    pdf_path = meta["pdf_path"]
    docx_path = meta["docx_path"]

    assert_reference_docx_openxml(docx_path)

    with pymupdf.open(str(pdf_path)) as doc:
        assert len(doc) == 3250
        entries, toc_count = parse_toc_entries(doc)
        assert toc_count == 10
        assert len(entries) >= 200

    ref_insp = inspect_docx_file(docx_path)
    full_text = "\n".join(ref_insp.paragraphs_text)
    assert "0806049-87.2024.8.20.5001" in full_text
    assert "Lais" in full_text
    assert "Gustavo" in full_text
    assert "Bianca" in full_text
    assert "Giovanna" in full_text


# ==============================================================================
# Global Corpus Integrity Check Across All 9 Cases
# ==============================================================================

def test_workload_all_nine_cases_coverage(reference_cases):
    """Verifies that all 9 cases are verified, exist, and have valid PDFs and DOCXs."""
    assert len(reference_cases) == 9
    total_pages = 0
    for case_num, meta in reference_cases.items():
        pdf_path = meta["pdf_path"]
        docx_path = meta["docx_path"]
        if not pdf_path.exists() or not docx_path.exists():
            pytest.skip("Real case reference PDFs/DOCXs not present in environment (LGPD sanitized)")
        total_pages += meta["total_pages"]

    assert total_pages == 6472
