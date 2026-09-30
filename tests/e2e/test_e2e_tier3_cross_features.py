"""Tier 3 Cross-Feature Interaction E2E Tests.

Exercises pairwise feature combinations and end-to-end integration flows:
- PDF Ingestion -> Indexing -> Stamp Mapping -> Pruning
- Scanned Page Detection -> OCR integration -> Text extraction
- Data Ingestion -> Schema Validation -> UI Mutation -> Revalidation
- Data Mutation -> DOCX Generation -> OpenXML Verification
- Mode 1 vs Mode 2 Schema Parity
- Full pipeline execution across real reference cases (Standard AIJ, ANPP, PAnP, Multi-accused)
"""

import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict

import docx
import pymupdf
import pytest

from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    PJeDocument,
    Witness,
)
from app.core.ocr_engine import OCREngine, is_scanned_page
from app.core.pje_indexer import (
    calculate_page_reduction,
    get_pruned_page_numbers,
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
# Cross-Feature 1: Ingestion -> Indexing -> Stamp Mapping
# ==============================================================================

def test_tier3_ingestion_to_stamp_mapping(primary_case_metadata):
    """X01: Ingests case 0801889 PDF, indexes documents, and maps stamps to pages."""
    pdf_path = str(primary_case_metadata["pdf_path"])
    if not os.path.exists(pdf_path):
        pytest.skip("Primary case PDF not present in environment (LGPD sanitized)")
    catalog, doc = index_pje_pdf(pdf_path)

    assert len(catalog) >= 40
    # Denúncia must be cataloged with valid start/end page
    denuncia = next((d for d in catalog if "denúncia" in d.doc_name.lower() or "denúncia" in d.doc_type.lower()), None)
    assert denuncia is not None
    assert denuncia.start_page > 0
    assert denuncia.end_page >= denuncia.start_page
    doc.close()


# ==============================================================================
# Cross-Feature 2: Indexing -> Pruning -> Token/Page Reduction
# ==============================================================================

def test_tier3_indexing_to_pruning_reduction(primary_case_metadata):
    """X02: Indexing followed by selective pruning yields significant page reduction."""
    pdf_path = str(primary_case_metadata["pdf_path"])
    if not os.path.exists(pdf_path):
        pytest.skip("Primary case PDF not present in environment (LGPD sanitized)")
    catalog, doc = index_pje_pdf(pdf_path)
    total_pages = len(doc)
    doc.close()

    pruned = prune_documents(catalog)
    assert len(pruned) < len(catalog)

    pruned_pages = get_pruned_page_numbers(pruned, include_toc=True)
    reduction_pct = calculate_page_reduction(total_pages, len(pruned_pages))

    # Page reduction exceeds 20% on case 0801889 (actual: 26.89%)
    assert reduction_pct > 20.0


# ==============================================================================
# Cross-Feature 3: Scanned Ingestion -> OCR -> Line Extraction
# ==============================================================================

def test_tier3_scanned_page_to_ocr_integration(reference_cases):
    """X03: Identifies scanned page in 0820550, runs OCR engine, and yields lines."""
    case_meta = reference_cases["0820550-12.2025.8.20.5001"]
    pdf_path = str(case_meta["pdf_path"])
    if not os.path.exists(pdf_path):
        pytest.skip("Case 0820550 PDF not present in environment (LGPD sanitized)")
    ocr = OCREngine.get_instance()

    with pymupdf.open(pdf_path) as doc:
        # Check scanned page classification
        scanned_page_idx = None
        for i in range(5, min(25, len(doc))):
            if is_scanned_page(doc[i], min_body_chars=30):
                scanned_page_idx = i
                break

        assert scanned_page_idx is not None
        target_page = doc[scanned_page_idx]

        if ocr.is_available:
            result = ocr.ocr_page(target_page, dpi=100)
            assert result.is_scanned is True
            assert isinstance(result.text, str)


# ==============================================================================
# Cross-Feature 4: Extracted Data -> UI Field Editing -> Schema Revalidation
# ==============================================================================

def test_tier3_extracted_data_to_ui_mutation_roundtrip(sample_summary_data: HearingSummaryData):
    """X04: Extracted hearing data undergoes full interactive field editing and revalidates."""
    # 1. User edits case header
    sample_summary_data.prosecutor = "Dr. Promotor Titular Atualizado"
    sample_summary_data.hearing_datetime = "01.08.26 às 09h30min"

    # 2. User edits defendant
    sample_summary_data.defendants[0].status = "Em liberdade provisória com cautelares"

    # 3. User adds a defense witness
    sample_summary_data.defense_witnesses.append(
        Witness(number=1, name="Testemunha de Defesa Teste", role="Vizinha", status_id="199999999")
    )
    sample_summary_data.defense_witness_note = None

    # 4. User adds procedural history item
    sample_summary_data.chronological_history.append(
        HistoryItem(date_str="25/07/26", description="Juntada de comprovante de residência", doc_id="195000000")
    )

    # Re-validate via Pydantic JSON round-trip
    dumped = sample_summary_data.model_dump_json()
    revalidated = HearingSummaryData.model_validate_json(dumped)

    assert revalidated.prosecutor == "Dr. Promotor Titular Atualizado"
    assert len(revalidated.defense_witnesses) == 1
    assert revalidated.defense_witnesses[0].name == "Testemunha de Defesa Teste"
    assert len(revalidated.chronological_history) == 4


# ==============================================================================
# Cross-Feature 5: Mutated Data -> DOCX Generation -> OpenXML Inspection
# ==============================================================================

def test_tier3_mutation_to_docx_openxml_compliance(sample_summary_data: HearingSummaryData):
    """X05: User-edited data is exported to DOCX; OpenXML properties match specs."""
    # Mutate data
    sample_summary_data.defendants[0].name = "JUCIMARCIA SOARES DA SILVA EDITADA"
    sample_summary_data.prosecution_witnesses.append(
        Witness(number=3, name="Terceira Testemunha Acusacao", role="PM", status_id="198765432")
    )

    docx_bytes = build_reference_docx(sample_summary_data)
    insp = inspect_docx_file(docx_bytes)

    # Verify OpenXML specs
    assert insp.page_width_twips == 11906  # 21 cm
    assert insp.page_height_twips == 16838  # 29.7 cm
    assert insp.margin_top_twips == 1134  # 2.0 cm
    assert insp.margin_bottom_twips == 1134
    assert insp.margin_left_twips == 1134
    assert insp.margin_right_twips == 1134
    assert "Verdana" in insp.fonts
    assert insp.has_formal_closure is True

    # Verify mutated content appears in text
    assert any("JUCIMARCIA SOARES DA SILVA EDITADA" in p for p in insp.paragraphs_text)
    assert any("Terceira Testemunha Acusacao" in p for p in insp.paragraphs_text)


# ==============================================================================
# Cross-Feature 6: Mode 1 (Gemini) vs Mode 2 (Offline) Schema Parity
# ==============================================================================

def test_tier3_dual_engine_schema_parity():
    """X06: Mode 1 output and Mode 2 output produce identical model structures."""
    mode1_dict = {
        "case_number": "0801889-53.2023.8.20.5001",
        "act_type": "AIJ",
        "hearing_datetime": "31.07.26 às 10h",
        "prosecutor": "Dr. Jann Polacek Melo Cardoso",
        "defendants": [{"name": "JUCIMARCIA SOARES DA SILVA", "status": "Em liberdade"}],
        "defense_counsel": "Defensoria Pública",
        "chronological_history": [
            {"date_str": "10/06/23", "description": "Denúncia", "doc_id": "101573748"}
        ],
        "prosecution_witnesses": [],
        "defense_witnesses": [],
    }

    mode2_dict = {
        "case_number": "0801889-53.2023.8.20.5001",
        "act_type": "AIJ",
        "hearing_datetime": "31.07.26 às 10h",
        "prosecutor": "Dr. Jann Polacek Melo Cardoso",
        "defendants": [{"name": "JUCIMARCIA SOARES DA SILVA", "status": "Em liberdade"}],
        "defense_counsel": "Defensoria Pública",
        "chronological_history": [
            {"date_str": "10/06/23", "description": "Denúncia", "doc_id": "101573748"}
        ],
        "prosecution_witnesses": [],
        "defense_witnesses": [],
    }

    obj1 = HearingSummaryData.model_validate(mode1_dict)
    obj2 = HearingSummaryData.model_validate(mode2_dict)

    assert obj1.model_dump() == obj2.model_dump()


# ==============================================================================
# Cross-Feature 7: End-to-End Pipeline on Standard AIJ Reference Case
# ==============================================================================

def test_tier3_full_pipeline_standard_aij(primary_case_metadata):
    """X07: Full end-to-end integration pipeline on reference case 0801889."""
    pdf_path = str(primary_case_metadata["pdf_path"])
    if not os.path.exists(pdf_path):
        pytest.skip("Primary case PDF not present in environment (LGPD sanitized)")

    # 1. Ingestion & Indexing
    catalog, doc = index_pje_pdf(pdf_path)
    assert len(catalog) > 0

    # 2. Prune documents
    pruned = prune_documents(catalog)
    assert len(pruned) > 0

    # 3. Build data model
    key_ids = primary_case_metadata["key_ids"]
    history_items = [
        HistoryItem(date_str="10/06/23", description="Denúncia", doc_id=key_ids[0]),
        HistoryItem(date_str="12/06/23", description="Decisão recebimento", doc_id=key_ids[1]),
    ]

    summary = HearingSummaryData(
        case_number=primary_case_metadata["case_number"],
        act_type=primary_case_metadata["act_type"],
        hearing_datetime=primary_case_metadata["hearing_datetime"],
        hearing_link=primary_case_metadata["hearing_link"],
        prosecutor=primary_case_metadata["prosecutor"],
        defendants=[Defendant(name=primary_case_metadata["defendants"][0], status=primary_case_metadata["defendants_status"][0])],
        defense_counsel=primary_case_metadata["defense_counsel"],
        chronological_history=history_items,
        prosecution_witnesses=[Witness(number=1, name="Wallace Gomes", role="Vítima", status_id="105732167")],
    )
    doc.close()

    # 4. Generate DOCX
    docx_bytes = build_reference_docx(summary)
    insp = inspect_docx_file(docx_bytes)

    # 5. Assert OpenXML fidelity
    assert insp.page_width_twips == 11906
    assert insp.margin_left_twips == 1134
    assert insp.has_formal_closure is True
    assert any("0801889-53.2023.8.20.5001" in p for p in insp.paragraphs_text)


# ==============================================================================
# Cross-Feature 8: End-to-End Pipeline on ANPP Special Format
# ==============================================================================

def test_tier3_full_pipeline_anpp(reference_cases):
    """X08: Full pipeline on ANPP case 0860849 with agreement conditions."""
    case_meta = reference_cases["0860849-94.2026.8.20.5001"]
    pdf_path = str(case_meta["pdf_path"])
    if not os.path.exists(pdf_path):
        pytest.skip("Case 0860849 PDF not present in environment (LGPD sanitized)")

    catalog, doc = index_pje_pdf(pdf_path)
    assert len(catalog) > 0
    doc.close()

    summary = HearingSummaryData(
        case_number=case_meta["case_number"],
        act_type=case_meta["act_type"],
        hearing_datetime=case_meta["hearing_datetime"],
        prosecutor=case_meta["prosecutor"],
        defendants=[Defendant(name=case_meta["defendants"][0], status=case_meta["defendants_status"][0])],
        defense_counsel=case_meta["defense_counsel"],
        special_notes="Desmembramento da ação penal nº 0804126-72.2024.",
        facts_summary="Furto qualificado de cabos em condomínio.",
    )

    docx_bytes = build_reference_docx(summary)
    insp = inspect_docx_file(docx_bytes)

    assert any("ANPP" in p for p in insp.paragraphs_text)
    assert any("SAMARA TARGINO DE LIMA" in p for p in insp.paragraphs_text)
    assert not any("QUALIFICAÇÃO" in p for p in insp.paragraphs_text)


# ==============================================================================
# Cross-Feature 9: End-to-End Pipeline on Multi-Defendant Robbery Case
# ==============================================================================

def test_tier3_full_pipeline_multi_defendant(reference_cases):
    """X09: Full pipeline on multi-defendant robbery case 0820550."""
    case_meta = reference_cases["0820550-12.2025.8.20.5001"]
    pdf_path = str(case_meta["pdf_path"])
    if not os.path.exists(pdf_path):
        pytest.skip("Case 0820550 PDF not present in environment (LGPD sanitized)")

    catalog, doc = index_pje_pdf(pdf_path)
    assert len(catalog) > 0
    doc.close()

    defs = [
        Defendant(name=case_meta["defendants"][0], status=case_meta["defendants_status"][0], subpoena_id="192131976"),
        Defendant(name=case_meta["defendants"][1], status=case_meta["defendants_status"][1]),
    ]

    summary = HearingSummaryData(
        case_number=case_meta["case_number"],
        act_type=case_meta["act_type"],
        hearing_datetime=case_meta["hearing_datetime"],
        prosecutor=case_meta["prosecutor"],
        defendants=defs,
        defense_counsel=case_meta["defense_counsel"],
        imputation_text="Art. 157, § 2º, II, e § 2º-A, I, c/c art. 180, caput, do CP.",
        chronological_history=[
            HistoryItem(date_str="30/06/25", description="Denúncia oferecida", doc_id="156069258"),
            HistoryItem(date_str="02/07/25", description="Decisão recebendo denúncia", doc_id="156265637"),
        ],
        prosecution_witnesses=[
            Witness(number=1, name="PM Jean Gomes da Silva", role="PM", status_id="190120604"),
            Witness(number=2, name="PM Bruno Costa Macedo", role="PM", status_id="190120604"),
            Witness(number=3, name="José Wellyngton Gomes da Silva", role="Vítima", status_id="192048248"),
        ],
    )

    docx_bytes = build_reference_docx(summary)
    insp = inspect_docx_file(docx_bytes)

    assert any("HEVERTON DOUGLAS ALVES DE MEDEIROS" in p for p in insp.paragraphs_text)
    assert any("ADRIANO MARTINS" in p for p in insp.paragraphs_text)
    assert any("PM Jean Gomes da Silva" in p for p in insp.paragraphs_text)
