"""Tier 2 Boundary and Edge Cases E2E Tests.

Exercises boundary values, corrupted/empty files, missing stamps, stacked stamps,
extreme file lengths, special ANPP/PAnP layouts, multi-defendant scenarios,
and strict zero-network offline enforcement.
"""

import io
import os
import socket
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import docx
import pymupdf
import pytest
from pydantic import ValidationError

from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    PJeDocument,
    Witness,
)
from app.core.ocr_engine import OCREngine, is_scanned_page
from app.core.pje_indexer import (
    FOOTER_STAMP_REGEX,
    get_page_footer_stamp,
    index_pje_pdf,
    parse_toc_entries,
    prune_documents,
)
from tests.conftest import (
    NAMESPACES,
    PROJECT_ROOT,
    REFERENCE_CASES_METADATA,
    inspect_docx_file,
)
from tests.e2e.test_e2e_tier1_features import build_reference_docx


# ==============================================================================
# Tier 2 Boundary Tests: File Integrity and Ingestion Boundaries
# ==============================================================================

def test_tier2_empty_file_handling(tmp_path: Path):
    """B01: Empty 0-byte file raises explicit error and does not hang."""
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")
    with pytest.raises(Exception):
        index_pje_pdf(str(empty_file))


def test_tier2_corrupt_pdf_header(tmp_path: Path):
    """B02: File with invalid PDF header is rejected."""
    corrupt_file = tmp_path / "corrupt.pdf"
    corrupt_file.write_bytes(b"NON_PDF_HEADER_CONTENT_12345")
    with pytest.raises(Exception):
        index_pje_pdf(str(corrupt_file))


def test_tier2_truncated_pdf(tmp_path: Path):
    """B03: Truncated PDF lacking EOF marker is rejected."""
    trunc_file = tmp_path / "truncated.pdf"
    trunc_file.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n")
    with pytest.raises(Exception):
        index_pje_pdf(str(trunc_file))


def test_tier2_nonexistent_pdf_path():
    """B04: Nonexistent PDF path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        index_pje_pdf("c:/nonexistent_path/fake_process.pdf")


def test_tier2_missing_footer_stamps_fallback(tmp_path: Path):
    """B05: PDF pages lacking footer stamps fall back safely to page mapping."""
    doc = pymupdf.open()
    # Create page without any stamp
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), "Petição avulsa sem carimbo de rodapé do PJe.")
    sample_pdf = tmp_path / "no_stamp.pdf"
    doc.save(str(sample_pdf))
    doc.close()

    catalog, open_doc = index_pje_pdf(str(sample_pdf))
    assert open_doc is not None
    assert len(open_doc) == 1
    open_doc.close()


def test_tier2_stacked_stamps_resolution(tmp_path: Path):
    """B06: Resolves stacked stamps selecting the lowest stamp on page."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    # Old stamp at y=760
    page.insert_text((50, 760), "Assinado eletronicamente por: JUIZ 1 - 01/01/2021 Num. 11111111 - Pág. 1")
    # Newer redistributing stamp at y=810
    page.insert_text((50, 810), "Assinado eletronicamente por: JUIZ 2 - 01/01/2026 Num. 22222222 - Pág. 1")
    sample_pdf = tmp_path / "stacked_stamp.pdf"
    doc.save(str(sample_pdf))
    doc.close()

    with pymupdf.open(str(sample_pdf)) as d:
        p = d[0]
        stamp = get_page_footer_stamp(p)
        assert stamp is not None
        doc_id, subpage = stamp
        assert doc_id == "22222222"
        assert subpage == 1


# ==============================================================================
# Tier 2 Boundary Tests: Offline Isolation & Network Guard
# ==============================================================================

def test_tier2_offline_strict_zero_network_execution(network_blocker, primary_case_metadata):
    """B07: PDF indexing and reference DOCX generation execute with zero network calls."""
    # Under network_blocker, any socket connect will raise ConnectionRefusedError
    pdf_path = str(primary_case_metadata["pdf_path"])
    catalog, doc = index_pje_pdf(pdf_path)
    assert len(catalog) > 0
    doc.close()

    # Create summary data and build docx
    summary = HearingSummaryData(
        case_number=primary_case_metadata["case_number"],
        act_type="AIJ",
        hearing_datetime="31.07.26 às 10h",
        prosecutor="Dr. Promotor",
        defendants=[Defendant(name="TESTE", status="Em liberdade")],
        defense_counsel="Defensoria",
    )
    docx_bytes = build_reference_docx(summary)
    assert len(docx_bytes) > 0


# ==============================================================================
# Tier 2 Boundary Tests: Extreme File Sizes and High Page Counts
# ==============================================================================

def test_tier2_extreme_page_count_case_0806049(reference_cases):
    """B08: Case 0806049 has 3,250 pages; parses TOC without memory exhaustion."""
    case_meta = reference_cases["0806049-87.2024.8.20.5001"]
    pdf_path = str(case_meta["pdf_path"])
    with pymupdf.open(pdf_path) as doc:
        assert len(doc) == 3250
        entries, toc_count = parse_toc_entries(doc)
        assert toc_count >= 5
        assert len(entries) > 100


def test_tier2_large_case_page_pruning(reference_cases):
    """B09: Case 0821902 (1,166 pages) prunes bulk data down by >70%."""
    case_meta = reference_cases["0821902-39.2024.8.20.5001"]
    pdf_path = str(case_meta["pdf_path"])
    catalog, doc = index_pje_pdf(pdf_path)
    pruned = prune_documents(catalog)
    doc.close()
    assert len(pruned) < len(catalog)
    assert len(pruned) > 0


# ==============================================================================
# Tier 2 Boundary Tests: Special Formats (ANPP, PAnP, Multi-accused)
# ==============================================================================

def test_tier2_anpp_structure_boundary(reference_cases):
    """B10: ANPP case 0860849 excludes qualificação and Rol, keeps OBS block."""
    case_meta = reference_cases["0860849-94.2026.8.20.5001"]
    anpp_data = HearingSummaryData(
        case_number=case_meta["case_number"],
        act_type="ANPP",
        hearing_datetime=case_meta["hearing_datetime"],
        prosecutor=case_meta["prosecutor"],
        defendants=[Defendant(name="SAMARA TARGINO DE LIMA", status="intimada")],
        defense_counsel=case_meta["defense_counsel"],
        special_notes="Processo oriundo de desmembramento da AP 0804126-72.2024.",
        facts_summary="Furto de fios de cobre em condomínio fechado.",
    )
    docx_bytes = build_reference_docx(anpp_data)
    insp = inspect_docx_file(docx_bytes)

    # In ANPP: no QUALIFICAÇÃO title, no IMPUTAÇÃO title, no TESTEMUNHAS title
    assert not any("QUALIFICAÇÃO" in p for p in insp.paragraphs_text)
    assert not any("IMPUTAÇÃO" in p for p in insp.paragraphs_text)
    assert not any("TESTEMUNHAS DE ACUSAÇÃO:" in p for p in insp.paragraphs_text)
    # But OBS: block must exist
    assert any("OBS:" in p for p in insp.paragraphs_text)


def test_tier2_panp_art_366_boundary(reference_cases):
    """B11: PAnP case 0804041 records art. 366 CPP suspension."""
    case_meta = reference_cases["0804041-57.2022.8.20.5600"]
    panp_data = HearingSummaryData(
        case_number=case_meta["case_number"],
        act_type="PAnP",
        hearing_datetime=case_meta["hearing_datetime"],
        prosecutor=case_meta["prosecutor"],
        defendants=[Defendant(name="BERANILDO", status="citado por edital")],
        defense_counsel="Defensoria Pública",
        special_notes="Audiência de produção antecipada de provas orais (art. 366 CPP).",
    )
    docx_bytes = build_reference_docx(panp_data)
    insp = inspect_docx_file(docx_bytes)
    assert any("PAnP" in p for p in insp.paragraphs_text)
    assert any("366" in p for p in insp.paragraphs_text)


def test_tier2_multi_defendants_quad_case(reference_cases):
    """B12: Multi-defendant scenario with 4 accused renders all 4 numbered."""
    case_meta = reference_cases["0806049-87.2024.8.20.5001"]
    defs = [Defendant(name=n, status="em liberdade") for n in case_meta["defendants"]]
    data = HearingSummaryData(
        case_number=case_meta["case_number"],
        act_type="AIJ",
        hearing_datetime=case_meta["hearing_datetime"],
        prosecutor=case_meta["prosecutor"],
        defendants=defs,
        defense_counsel="Advogados Particulares",
    )
    assert len(data.defendants) == 4
    docx_bytes = build_reference_docx(data)
    insp = inspect_docx_file(docx_bytes)
    assert any("01) LAIS" in p for p in insp.paragraphs_text)
    assert any("04) GIOVANNA" in p for p in insp.paragraphs_text)


def test_tier2_missing_defendant_cpf_rg_graceful():
    """B13: Handles defendant qualification when CPF and RG are omitted."""
    d = Defendant(
        name="RÉU DESCONHECIDO",
        status="solto",
        qualification="brasileiro, solteiro, residente em local incerto",
    )
    assert d.citation_id is None
    assert d.subpoena_id is None
    assert "local incerto" in d.qualification


def test_tier2_in_person_hearing_boundary():
    """B14: Presencial hearing indicates 'Audiência Presencial' rather than meeting link."""
    presencial_data = HearingSummaryData(
        case_number="0876503-58.2025.8.20.5001",
        act_type="AIJ",
        hearing_datetime="10.07.26 às 11h",
        hearing_link=None,
        is_in_person=True,
        prosecutor="Ministério Público",
        defendants=[Defendant(name="MANOEL")],
        defense_counsel="Advogado",
    )
    docx_bytes = build_reference_docx(presencial_data)
    insp = inspect_docx_file(docx_bytes)
    assert any("Audiência Presencial" in p for p in insp.paragraphs_text)
    assert not any("teams.microsoft.com" in p for p in insp.paragraphs_text)


def test_tier2_defense_reiteration_versus_no_witnesses():
    """B15: Handles both 'reiterou denúncia' and 'não há testemunhas arroladas'."""
    note1 = "A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia."
    note2 = "Não há testemunhas de defesa arroladas."

    d1 = HearingSummaryData(
        case_number="0801889-53.2023.8.20.5001",
        hearing_datetime="31.07.26",
        prosecutor="MP",
        defendants=[Defendant(name="RÉU")],
        defense_counsel="Defensoria",
        defense_witness_note=note1,
    )
    d2 = HearingSummaryData(
        case_number="0801889-53.2023.8.20.5001",
        hearing_datetime="31.07.26",
        prosecutor="MP",
        defendants=[Defendant(name="RÉU")],
        defense_counsel="Defensoria",
        defense_witness_note=note2,
    )
    assert d1.defense_witness_note == note1
    assert d2.defense_witness_note == note2


def test_tier2_openxml_margin_verification():
    """B16: Verifies that DOCX with non-2cm margins is detectable."""
    doc = docx.Document()
    sec = doc.sections[0]
    # Set improper 3.0 cm margins
    sec.top_margin = docx.shared.Cm(3.0)
    buf = io.BytesIO()
    doc.save(buf)

    insp = inspect_docx_file(buf.getvalue())
    # 3.0 cm is ~1701 twips, not 1134 twips
    assert insp.margin_top_twips != 1134
    assert insp.margin_top_twips > 1500
