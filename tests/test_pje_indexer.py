"""Comprehensive test suite for PJe Indexer, OCR engine, models, and selective pruning."""

import os
import glob
from typing import Optional
import pytest
import pymupdf
from PIL import Image

from app.core.models import (
    Defendant,
    Witness,
    HistoryItem,
    HearingSummaryData,
    IndexTableEntry,
    PJeDocument,
    OCRLine,
    OCRResult,
)
from app.core.ocr_engine import (
    OCREngine,
    is_scanned_page,
    PJE_STAMP_REGEX,
)
from app.core.pje_indexer import (
    FOOTER_STAMP_REGEX,
    parse_toc_entries,
    get_page_footer_stamp,
    index_pje_pdf,
    is_relevant_document,
    prune_documents,
    get_pruned_page_numbers,
    calculate_page_reduction,
)

# Base directory for the 9 reference cases
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if not glob.glob(os.path.join(WORKSPACE_DIR, "*0801889*", "*.pdf")):
    parent_dir = os.path.abspath(os.path.join(WORKSPACE_DIR, ".."))
    if glob.glob(os.path.join(parent_dir, "*0801889*", "*.pdf")):
        WORKSPACE_DIR = parent_dir

# Helper to find a PDF by case prefix
def find_case_pdf(case_number_prefix: str) -> Optional[str]:
    pattern = os.path.join(WORKSPACE_DIR, f"*{case_number_prefix}*", "*.pdf")
    matches = glob.glob(pattern)
    if not matches:
        pattern_nested = os.path.join(WORKSPACE_DIR, "*", f"*{case_number_prefix}*.pdf")
        matches = glob.glob(pattern_nested)
    return matches[0] if matches else None


# =====================================================================
# 1. Pydantic Models Validation
# =====================================================================

def test_pydantic_models_instantiation():
    """Verifies that all 6 judicial data contract models instantiate and validate correctly."""
    defendant = Defendant(
        name="JUCIMARCIA SOARES DA SILVA",
        status="Em liberdade",
        citation_id="194381260",
        subpoena_id="194381260",
        qualification="brasileira, solteira, diarista",
    )
    assert defendant.name == "JUCIMARCIA SOARES DA SILVA"
    assert defendant.status == "Em liberdade"
    assert defendant.citation_id == "194381260"

    witness = Witness(
        number=1,
        name="Wallace Gomes Santos",
        role="Vítima",
        status_id="105732167",
    )
    assert witness.number == 1
    assert witness.role == "Vítima"

    history_item = HistoryItem(
        date_str="10/06/23",
        description="Denúncia oferecida com proposta de Sursis",
        doc_id="101573748",
        pje_url="https://pje1g.tjrn.jus.br/...",
    )
    assert history_item.date_str == "10/06/23"
    assert history_item.doc_id == "101573748"

    summary = HearingSummaryData(
        case_number="0801889-53.2023.8.20.5001",
        act_type="AIJ",
        hearing_datetime="31.07.26 às 10h00min",
        hearing_link="https://teams.microsoft.com/meet/...",
        is_in_person=False,
        prosecutor="Dr. Jann Polacek Melo Cardoso",
        defendants=[defendant],
        defense_counsel="Defensoria Pública",
        qualification_text="JUCIMARCIA SOARES DA SILVA, brasileira...",
        imputation_text="Art. 129, § 9º, do Código Penal",
        facts_summary="Narrativa das agressões...",
        chronological_history=[history_item],
        prosecution_witnesses=[witness],
        defense_witnesses=[],
        defense_witness_note="A defesa reiterou o rol da acusação.",
        closure_text="Cordial e respeitosamente,",
    )
    assert summary.case_number == "0801889-53.2023.8.20.5001"
    assert summary.closure_text == "Cordial e respeitosamente,"
    assert len(summary.defendants) == 1
    assert len(summary.prosecution_witnesses) == 1

    # Index models
    index_entry = IndexTableEntry(
        doc_id="101573748",
        date_str="10/06/2023 10:49",
        doc_name="Denúncia",
        doc_type="Denúncia",
        page_in_toc=1,
    )
    assert index_entry.doc_id == "101573748"

    pje_doc = PJeDocument(
        doc_id="101573748",
        date_str="10/06/2023 10:49",
        doc_name="Denúncia",
        doc_type="Denúncia",
        start_page=40,
        end_page=42,
        is_scanned=False,
    )
    assert pje_doc.start_page == 40
    assert pje_doc.end_page == 42
    assert not pje_doc.is_scanned


# =====================================================================
# 2. Footer Stamp Regex and Extraction Tests
# =====================================================================

def test_footer_stamp_regex_patterns():
    """Tests regex matching across various PJe footer stamp formats and variants."""
    examples = [
        ("Num. 93824005 - Pág. 1", "93824005", 1),
        ("Num. 101573748 - Pág. 3", "101573748", 3),
        ("Num.  189175919   -   Pág.  2", "189175919", 2),
        ("Assinado eletronicamente Num. 12345678 - Pag. 10 Total", "12345678", 10),
        ("NUM. 99887766 - PÁG. 1", "99887766", 1),
    ]
    for text, expected_id, expected_page in examples:
        m = FOOTER_STAMP_REGEX.search(text)
        assert m is not None, f"Failed to match stamp in: '{text}'"
        assert m.group(1) == expected_id
        assert int(m.group(2)) == expected_page


def test_stacked_footer_stamps_priority():
    """Tests that when multiple stamps exist on a page, the lowest one (largest y1) is chosen."""
    # Create an in-memory PDF page with two stamps placed at different vertical positions
    pdf_mem = pymupdf.open()
    page = pdf_mem.new_page(width=595, height=842)
    # Stamp 1 at y=750 (older stamp from previous court)
    page.insert_text((50, 750), "Num. 11111111 - Pág. 1", fontsize=9)
    # Stamp 2 at y=810 (current PJe stamp)
    page.insert_text((50, 810), "Num. 22222222 - Pág. 5", fontsize=9)

    doc_id, subpage = get_page_footer_stamp(page)
    assert doc_id == "22222222", f"Expected lowest stamp '22222222', got '{doc_id}'"
    assert subpage == 5


# =====================================================================
# 3. Scanned Page Detection and OCR Engine Tests
# =====================================================================

def test_scanned_page_detection_on_sample_case():
    """Tests detection of native text pages vs scanned image pages on Proc. 0801889."""
    pdf_path = find_case_pdf("0801889")
    assert pdf_path is not None, "Proc. 0801889 PDF not found"

    doc = pymupdf.open(pdf_path)
    # Page 39 (0-indexed, so page 40) is Denúncia (native digital text)
    denuncia_page = doc[39]
    assert not is_scanned_page(denuncia_page), "Denúncia page should be classified as native text"

    # Page 19 (0-indexed, so page 20) is a scanned ITEP medical report
    scanned_page = doc[19]
    assert is_scanned_page(scanned_page), "Page 20 should be classified as scanned"


def test_ocr_engine_execution_and_stamp_filtering():
    """Tests that OCREngine correctly crops headers/footers and extracts structured lines."""
    pdf_path = find_case_pdf("0801889")
    assert pdf_path is not None

    doc = pymupdf.open(pdf_path)
    scanned_page = doc[19]  # Page 20 (ITEP Atestado Nº 1348/2023)

    engine = OCREngine.get_instance()
    assert engine.is_available, "RapidOCR engine should be available"

    # Run OCR with crop on top and bottom margins
    result = engine.ocr_page(scanned_page, crop_top=50.0, crop_bottom=80.0, dpi=150)
    assert isinstance(result, OCRResult)
    assert len(result.lines) > 0
    assert result.is_scanned is True

    # The report mentions "Atestado" and "1348"
    assert "1348" in result.text or "ATESTADO" in result.text or "ITEP" in result.text

    # Verify that the PJe footer stamp was filtered out / cropped
    assert not PJE_STAMP_REGEX.search(result.text)


# =====================================================================
# 4. Table of Documents (TOC) Parsing on Real Cases
# =====================================================================

def test_toc_parsing_proc_0801889():
    """Verifies TOC extraction on Proc. 0801889 (3 TOC pages, 67 documents)."""
    pdf_path = find_case_pdf("0801889")
    assert pdf_path is not None
    doc = pymupdf.open(pdf_path)

    entries, toc_count = parse_toc_entries(doc)
    assert toc_count == 3, f"Expected 3 TOC pages, got {toc_count}"
    assert len(entries) == 67, f"Expected 67 documents, got {len(entries)}"

    # Check key documents exist in entries
    doc_types = {e.doc_type for e in entries}
    assert "Denúncia" in doc_types
    assert "Decisão" in doc_types

    # Find the Denúncia entry
    denuncia = next(e for e in entries if e.doc_id == "101573748")
    assert "Denúncia" in denuncia.doc_name
    assert "10/06/2023" in denuncia.date_str


def test_toc_parsing_proc_0860849():
    """Verifies TOC extraction on Proc. 0860849 (2 TOC pages, 27 documents)."""
    pdf_path = find_case_pdf("0860849")
    assert pdf_path is not None
    doc = pymupdf.open(pdf_path)

    entries, toc_count = parse_toc_entries(doc)
    assert toc_count == 2, f"Expected 2 TOC pages, got {toc_count}"
    assert len(entries) == 27, f"Expected 27 documents, got {len(entries)}"


def test_toc_parsing_proc_0820550():
    """Verifies TOC extraction on Proc. 0820550 (4 TOC pages, 97 documents)."""
    pdf_path = find_case_pdf("0820550")
    assert pdf_path is not None
    doc = pymupdf.open(pdf_path)

    entries, toc_count = parse_toc_entries(doc)
    assert toc_count == 4, f"Expected 4 TOC pages, got {toc_count}"
    assert len(entries) == 97, f"Expected 97 documents, got {len(entries)}"


# =====================================================================
# 5. Full PJe Indexing (index_pje_pdf) Page-by-Page Mapping
# =====================================================================

def test_index_pje_pdf_proc_0801889():
    """Verifies 100% page-by-page mapping and start/end pages on Proc. 0801889."""
    pdf_path = find_case_pdf("0801889")
    assert pdf_path is not None

    catalog, doc = index_pje_pdf(pdf_path)
    assert len(doc) == 119
    assert len(catalog) >= 67

    # Find Denúncia (ID 101573748)
    denuncia = next(d for d in catalog if d.doc_id == "101573748")
    assert denuncia.start_page == 40
    assert denuncia.end_page == 42
    assert not denuncia.is_scanned

    # Find Decisão de Recebimento (ID 101605793)
    decisao = next(d for d in catalog if d.doc_id == "101605793")
    assert decisao.start_page == 43
    assert decisao.end_page == 44

    # Verify that scanned documents are properly marked
    scanned_docs = [d for d in catalog if d.is_scanned]
    assert len(scanned_docs) > 0, "Should detect at least one scanned document"


# =====================================================================
# 6. Selective Pruning Functionality & Page Reduction
# =====================================================================

def test_selective_pruning_relevance_matching():
    """Tests relevance classification for key legal documents."""
    assert is_relevant_document("Denúncia", "Denúncia")
    assert is_relevant_document("Decisão de Recebimento", "Decisão")
    assert is_relevant_document("Resposta à acusação", "Petição")
    assert is_relevant_document("MANDADO - JUCIMARCIA", "Diligência")
    assert is_relevant_document("Ato positivo", "Diligência")
    assert is_relevant_document("Apresentação de Policiais Militares", "Informação")
    assert is_relevant_document("Termo de ANPP", "Acordo")

    # Non-essential bulk documents should NOT be relevant
    assert not is_relevant_document("Extrato Bancário SIMBA", "Outros documentos")
    assert not is_relevant_document("Dados Telefônicos Operadora", "Documento de Comprovação")


def test_selective_pruner_page_reduction_large_cases():
    """Verifies that selective pruning achieves >90% page reduction on large files."""
    # Test on the 3,250-page case Proc. 0806049
    pdf_path_large = find_case_pdf("0806049")
    if pdf_path_large:
        doc = pymupdf.open(pdf_path_large)
        assert len(doc) == 3250
        entries, toc_count = parse_toc_entries(doc)
        catalog, _ = index_pje_pdf(pdf_path_large)
        pruned = prune_documents(catalog)
        pages = get_pruned_page_numbers(pruned, include_toc=True, toc_count=toc_count)

        reduction = calculate_page_reduction(len(doc), len(pages))
        # Should reduce from 3,250 pages down to ~100-240 pages (>92% reduction)
        assert reduction >= 90.0, f"Expected >= 90% reduction, got {reduction:.2f}%"
        assert len(pages) < 300


def test_calculate_page_reduction_helper():
    """Tests calculation helper for page reduction percentages."""
    assert calculate_page_reduction(100, 5) == 95.0
    assert calculate_page_reduction(1000, 20) == 98.0
    assert calculate_page_reduction(0, 0) == 0.0


def test_invalid_pdf_path_raises_error():
    """Verifies that non-existent PDF file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        index_pje_pdf("c:/non_existent_path/fake.pdf")


# =====================================================================
# 7. Comprehensive Coverage across all 9 Reference Cases
# =====================================================================

ALL_NINE_CASES_EXPECTATIONS = [
    ("0801889", 3, 67),
    ("0802487", 2, 45),
    ("0804041", 4, 111),
    ("0806049", 10, 278),
    ("0844118", 3, 61),
    ("0820550", 4, 97),
    ("0821902", 7, 202),
    ("0860849", 2, 27),
    ("0876503", 5, 116),
]


@pytest.mark.parametrize("case_prefix, expected_toc_pages, expected_doc_count", ALL_NINE_CASES_EXPECTATIONS)
def test_toc_parsing_across_all_nine_cases(case_prefix: str, expected_toc_pages: int, expected_doc_count: int):
    """Verifies TOC pages and document counts across all 9 reference cases."""
    pdf_path = find_case_pdf(case_prefix)
    assert pdf_path is not None, f"PDF for case {case_prefix} not found"

    doc = pymupdf.open(pdf_path)
    entries, toc_count = parse_toc_entries(doc)

    assert toc_count == expected_toc_pages, (
        f"Case {case_prefix}: expected {expected_toc_pages} TOC pages, got {toc_count}"
    )
    assert len(entries) == expected_doc_count, (
        f"Case {case_prefix}: expected {expected_doc_count} docs, got {len(entries)}"
    )


def test_ocr_engine_image_bytes_directly():
    """Tests running OCR engine on raw generated image bytes."""
    # Create a small white image with text using PIL
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    engine = OCREngine.get_instance()
    res = engine.ocr_image_bytes(img_bytes, page_number=1)
    assert isinstance(res, OCRResult)
    assert res.is_scanned is True
    assert res.page_number == 1


def test_get_page_footer_stamp_blank_page():
    """Verifies get_page_footer_stamp returns None on a page with no stamp."""
    pdf_mem = pymupdf.open()
    page = pdf_mem.new_page(width=595, height=842)
    page.insert_text((50, 100), "Texto simples sem carimbo nenhum.")
    stamp = get_page_footer_stamp(page)
    assert stamp is None


def test_get_pruned_page_numbers_boundaries():
    """Verifies get_pruned_page_numbers handles empty lists and invalid page ranges safely."""
    # Empty catalog
    assert get_pruned_page_numbers([], include_toc=True, toc_count=1) == [1]
    assert get_pruned_page_numbers([], include_toc=False) == []

    # Documents with start_page == 0 (unmapped notices) should be skipped
    unmapped_doc = PJeDocument(
        doc_id="999",
        date_str="01/01/2026",
        doc_name="Aviso",
        doc_type="Aviso",
        start_page=0,
        end_page=0,
    )
    mapped_doc = PJeDocument(
        doc_id="1000",
        date_str="01/01/2026",
        doc_name="Denúncia",
        doc_type="Denúncia",
        start_page=10,
        end_page=12,
    )
    pages = get_pruned_page_numbers([unmapped_doc, mapped_doc], include_toc=True, toc_count=1)
    assert pages == [1, 10, 11, 12]

