"""Test configuration, fixtures, and helpers for the Judicial Case Summary E2E Test Suite.

Provides:
- Reference cases metadata mapping across all 9 real-world PJe cases.
- DOCX OpenXML structural inspectors (A4 dimensions, 2cm margins, Verdana fonts, line spacing).
- Sample test models adhering to app.core.models.HearingSummaryData.
- Network isolation verification fixtures for 100% offline mode.
"""

import io
import os
import re
import socket
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import docx
import pytest

from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    IndexTableEntry,
    PJeDocument,
    Witness,
)

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Check if reference cases live in current root or parent root (e.g. when run inside gitpost/)
if not (PROJECT_ROOT / "Proc. 0801889-53.2023.8.20.5001").exists() and (PROJECT_ROOT.parent / "Proc. 0801889-53.2023.8.20.5001").exists():
    CASES_DIR = PROJECT_ROOT.parent
else:
    CASES_DIR = PROJECT_ROOT

HAS_REAL_CASES = (CASES_DIR / "Proc. 0801889-53.2023.8.20.5001").exists()

# XML Namespaces for OpenXML inspection
NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

# The 9 reference cases accurately mapped to their actual on-disk locations
REFERENCE_CASES_METADATA: Dict[str, Dict[str, Any]] = {
    "0801889-53.2023.8.20.5001": {
        "case_number": "0801889-53.2023.8.20.5001",
        "folder": CASES_DIR / "Proc. 0801889-53.2023.8.20.5001",
        "pdf_path": CASES_DIR / "Proc. 0801889-53.2023.8.20.5001" / "Proc. 0801889-53.2023.8.20.5001.pdf",
        "docx_path": CASES_DIR / "Proc. 0801889-53.2023.8.20.5001" / "Resumo - Proc. 0801889-53.2023.8.20.5001 AIJ 31.07.26 às 10h00min.docx",
        "act_type": "AIJ",
        "hearing_datetime": "31.07.26 às 10h00min",
        "hearing_link": "https://teams.microsoft.com/meet/284792802358140?p=MGiGbSP2E0MO1Jpl96",
        "is_in_person": False,
        "prosecutor": "Dr. Jann Polacek Melo Cardoso",
        "defendants": ["JUCIMARCIA SOARES DA SILVA"],
        "defendants_status": ["Ré respondendo ao processo em liberdade"],
        "defense_counsel": "Defensoria Pública - Dr. Paulo Maycon",
        "key_ids": [
            "101573748", "101605793", "105732167", "163508199",
            "179799740", "189177385", "189907759", "189952352",
            "192577483", "194381260", "191239678"
        ],
        "total_pages": 119,
        "scanned_pages_pct": 10.1,
    },
    "0802487-75.2026.8.20.5300": {
        "case_number": "0802487-75.2026.8.20.5300",
        "folder": CASES_DIR / "Proc. 0802487-75.2026.8.20.5300",
        "pdf_path": CASES_DIR / "Proc. 0802487-75.2026.8.20.5300" / "Proc. 0802487-75.2026.8.20.5300.pdf",
        "docx_path": CASES_DIR / "Proc. 0802487-75.2026.8.20.5300" / "Resumo - Proc. 0802487-75.2026.8.20.5300 AIJ 31.07.26 às 11h00min .docx",
        "act_type": "AIJ",
        "hearing_datetime": "31.07.26 às 11h00min",
        "is_in_person": False,
        "prosecutor": "Ministério Público Estadual",
        "defendants": ["GEAN"],
        "defendants_status": ["réu preso"],
        "defense_counsel": "Defensoria Pública",
        "key_ids": ["192131976"],
        "total_pages": 209,
        "scanned_pages_pct": 14.4,
    },
    "0804041-57.2022.8.20.5600": {
        "case_number": "0804041-57.2022.8.20.5600",
        "folder": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600",
        "pdf_path": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600" / "Proc. 0804041-57.2022.8.20.5600.pdf",
        "docx_path": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600" / "Resumo - 0804041-57.2022.8.20.5600 PAnP 23.07.26 às 13h00min .docx",
        "act_type": "PAnP",
        "hearing_datetime": "23.07.26 às 13h00min",
        "is_in_person": False,
        "prosecutor": "Ministério Público Estadual",
        "defendants": ["BERANILDO"],
        "defendants_status": ["citado por edital"],
        "defense_counsel": "Defensoria Pública",
        "key_ids": ["180815370"],
        "total_pages": 212,
        "scanned_pages_pct": 20.3,
    },
    "0806049-87.2024.8.20.5001": {
        "case_number": "0806049-87.2024.8.20.5001",
        "folder": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600",
        "pdf_path": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600" / "Proc. 0806049-87.2024.8.20.5001.pdf",
        "docx_path": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600" / "Resumo - 0806049-87.2024.8.20.5001 - AIJ - 17.07.26 - 10h.docx",
        "act_type": "AIJ",
        "hearing_datetime": "17.07.26 às 10h",
        "is_in_person": False,
        "prosecutor": "GAECO - Grupo de Atuação Especial de Combate ao Crime Organizado",
        "defendants": ["LAIS", "GUSTAVO", "BIANCA", "GIOVANNA"],
        "defendants_status": ["em liberdade"],
        "defense_counsel": "Advogados Particulares",
        "key_ids": ["189061694", "189175919"],
        "total_pages": 3250,
        "scanned_pages_pct": 2.5,
    },
    "0820550-12.2025.8.20.5001": {
        "case_number": "0820550-12.2025.8.20.5001",
        "folder": CASES_DIR / "Proc. 0820550-12.2025.8.20.5001",
        "pdf_path": CASES_DIR / "Proc. 0820550-12.2025.8.20.5001" / "Proc. 0820550-12.2025.8.20.5001.pdf",
        "docx_path": CASES_DIR / "Proc. 0820550-12.2025.8.20.5001" / "Resumo - 0820550-12.2025.8.20.5001 - AIJ 17.07.26 - 09h.docx",
        "act_type": "AIJ",
        "hearing_datetime": "17.07.26 às 09h",
        "is_in_person": False,
        "prosecutor": "Ministério Público Estadual",
        "defendants": ["HEVERTON DOUGLAS ALVES DE MEDEIROS", "ADRIANO MARTINS"],
        "defendants_status": ["réu preso", "não citado e não localizado"],
        "defense_counsel": "Advogado Particular / Defensoria Pública",
        "key_ids": [
            "147416808", "156069258", "156265637", "173310111",
            "174875152", "179108500", "180620731", "180686771",
            "180815370", "186825748", "189093604", "190120604",
            "190701405", "192048248", "192131976"
        ],
        "total_pages": 190,
        "scanned_pages_pct": 41.6,
    },
    "0821902-39.2024.8.20.5001": {
        "case_number": "0821902-39.2024.8.20.5001",
        "folder": CASES_DIR / "Proc. 0821902-39.2024.8.20.5001",
        "pdf_path": CASES_DIR / "Proc. 0821902-39.2024.8.20.5001" / "Proc. 0821902-39.2024.8.20.5001.pdf",
        "docx_path": CASES_DIR / "Proc. 0821902-39.2024.8.20.5001" / "Resumo - 0821902-39.2024.8.20.5001 - AIJ - 13.07.26 às 14h00min.docx",
        "act_type": "AIJ",
        "hearing_datetime": "13.07.26 às 14h00min",
        "is_in_person": False,
        "prosecutor": "Ministério Público Estadual",
        "defendants": ["LUANNA"],
        "defendants_status": ["em liberdade"],
        "defense_counsel": "Advogado Particular",
        "key_ids": ["189061694"],
        "total_pages": 1166,
        "scanned_pages_pct": 19.5,
    },
    "0844118-57.2025.8.20.5001": {
        "case_number": "0844118-57.2025.8.20.5001",
        "folder": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600",
        "pdf_path": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600" / "Proc. 0844118-57.2025.8.20.5001.pdf",
        "docx_path": CASES_DIR / "Proc. 0804041-57.2022.8.20.5600" / "Resumo - 0844118-57.2025.8.20.5001 AIJ 24.07.26 às 11h.docx",
        "act_type": "AIJ",
        "hearing_datetime": "24.07.26 às 11h",
        "is_in_person": False,
        "prosecutor": "5ª Promotoria de Natal",
        "defendants": ["ABNER BARBOSA DA SILVA"],
        "defendants_status": ["em liberdade"],
        "defense_counsel": "Defensoria Pública",
        "key_ids": [
            "154686213", "154886585", "178221008", "178312636",
            "181171275", "183941769", "189482358", "190792716",
            "192000162", "191993720", "192000151"
        ],
        "total_pages": 336,
        "scanned_pages_pct": 2.4,
    },
    "0860849-94.2026.8.20.5001": {
        "case_number": "0860849-94.2026.8.20.5001",
        "folder": CASES_DIR / "Proc. 0860849-94.2026.8.20.5001",
        "pdf_path": CASES_DIR / "Proc. 0860849-94.2026.8.20.5001" / "Proc. 0860849-94.2026.8.20.5001.pdf",
        "docx_path": CASES_DIR / "Proc. 0860849-94.2026.8.20.5001" / "Resumo - 0860849-94.2026.8.20.5001 ANPP 24.07.2026 às 11h25.docx",
        "act_type": "ANPP",
        "hearing_datetime": "24.07.2026 às 11h25",
        "is_in_person": False,
        "prosecutor": "Ministério Público Estadual",
        "defendants": ["SAMARA TARGINO DE LIMA"],
        "defendants_status": ["intimada"],
        "defense_counsel": "Dr. Francisco de Assis dos Santos - OAB RN 13.792",
        "key_ids": [
            "191909557", "191909567", "191909572", "191912979",
            "192155666", "193620153"
        ],
        "total_pages": 480,
        "scanned_pages_pct": 0.6,
    },
    "0876503-58.2025.8.20.5001": {
        "case_number": "0876503-58.2025.8.20.5001",
        "folder": CASES_DIR / "Proc. 0876503-58.2025.8.20.5001",
        "pdf_path": CASES_DIR / "Proc. 0876503-58.2025.8.20.5001" / "Proc. 0876503-58.2025.8.20.5001.pdf",
        "docx_path": CASES_DIR / "Proc. 0876503-58.2025.8.20.5001" / "Resumo - 0876503-58.2025.8.20.5001 - 11h - 10.07.26.docx",
        "act_type": "AIJ",
        "hearing_datetime": "10.07.26 às 11h",
        "is_in_person": False,
        "prosecutor": "Ministério Público Estadual",
        "defendants": [
            "MANOEL PAULINO DA SILVA SOBRINHO",
            "JOSUEL FARIAS DA SILVA",
            "FELIPE FARIAS DA SILVA"
        ],
        "defendants_status": ["intimado", "intimado", "intimado"],
        "defense_counsel": "Dr. José Sinfrônio de Oliveira Mariz Filho (OAB/PB 18.959)",
        "key_ids": [
            "166877018", "168079481", "178692514", "182668023",
            "185274100", "185306620", "186452933", "186633421",
            "186504161", "186678830", "187069583", "189061694",
            "189175919", "191482391", "191991522", "191991507",
            "191994319"
        ],
        "total_pages": 510,
        "scanned_pages_pct": 15.5,
    },
}


# ==============================================================================
# OpenXML Inspection Helpers
# ==============================================================================

class DocxInspectionResult:
    """Encapsulates properties extracted directly from OpenXML zip package."""
    def __init__(
        self,
        page_width_twips: int,
        page_height_twips: int,
        page_orient: str,
        margin_top_twips: int,
        margin_bottom_twips: int,
        margin_left_twips: int,
        margin_right_twips: int,
        line_spacings: List[str],
        justifications: List[str],
        fonts: List[str],
        paragraphs_text: List[str],
        hyperlink_urls: List[str],
        has_formal_closure: bool,
    ):
        self.page_width_twips = page_width_twips
        self.page_height_twips = page_height_twips
        self.page_orient = page_orient
        self.margin_top_twips = margin_top_twips
        self.margin_bottom_twips = margin_bottom_twips
        self.margin_left_twips = margin_left_twips
        self.margin_right_twips = margin_right_twips
        self.line_spacings = line_spacings
        self.justifications = justifications
        self.fonts = fonts
        self.paragraphs_text = paragraphs_text
        self.hyperlink_urls = hyperlink_urls
        self.has_formal_closure = has_formal_closure


def inspect_docx_file(docx_input: Any) -> DocxInspectionResult:
    """Inspects a .docx file path, bytes, or BytesIO directly via OpenXML zip."""
    if isinstance(docx_input, (str, Path)):
        zip_file = zipfile.ZipFile(docx_input)
    elif isinstance(docx_input, bytes):
        zip_file = zipfile.ZipFile(io.BytesIO(docx_input))
    elif isinstance(docx_input, io.BytesIO):
        zip_file = zipfile.ZipFile(docx_input)
    else:
        raise ValueError(f"Unsupported docx_input type: {type(docx_input)}")

    with zip_file:
        doc_xml_content = zip_file.read("word/document.xml")
        root = ET.fromstring(doc_xml_content)

        # Page setup
        sect_pr = root.find(".//w:sectPr", NAMESPACES)
        pg_sz = sect_pr.find("w:pgSz", NAMESPACES) if sect_pr is not None else None
        pg_mar = sect_pr.find("w:pgMar", NAMESPACES) if sect_pr is not None else None

        page_width = int(pg_sz.attrib.get(f"{{{NAMESPACES['w']}}}w", "0")) if pg_sz is not None else 0
        page_height = int(pg_sz.attrib.get(f"{{{NAMESPACES['w']}}}h", "0")) if pg_sz is not None else 0
        page_orient = pg_sz.attrib.get(f"{{{NAMESPACES['w']}}}orient", "portrait") if pg_sz is not None else "portrait"

        m_top = int(pg_mar.attrib.get(f"{{{NAMESPACES['w']}}}top", "0")) if pg_mar is not None else 0
        m_bottom = int(pg_mar.attrib.get(f"{{{NAMESPACES['w']}}}bottom", "0")) if pg_mar is not None else 0
        m_left = int(pg_mar.attrib.get(f"{{{NAMESPACES['w']}}}left", "0")) if pg_mar is not None else 0
        m_right = int(pg_mar.attrib.get(f"{{{NAMESPACES['w']}}}right", "0")) if pg_mar is not None else 0

        # Spacings, Justifications, Fonts, and Paragraphs
        line_spacings: List[str] = []
        justifications: List[str] = []
        fonts: List[str] = []
        paragraphs_text: List[str] = []

        for p in root.findall(".//w:p", NAMESPACES):
            # Text
            texts = [t.text for t in p.findall(".//w:t", NAMESPACES) if t.text]
            full_text = "".join(texts).strip()
            paragraphs_text.append(full_text)

            # Spacing
            spacing = p.find(".//w:spacing", NAMESPACES)
            if spacing is not None:
                line = spacing.attrib.get(f"{{{NAMESPACES['w']}}}line")
                if line:
                    line_spacings.append(line)

            # Justification
            jc = p.find(".//w:jc", NAMESPACES)
            if jc is not None:
                val = jc.attrib.get(f"{{{NAMESPACES['w']}}}val")
                if val:
                    justifications.append(val)

            # Fonts in runs
            for r in p.findall(".//w:r", NAMESPACES):
                r_fonts = r.find(".//w:rFonts", NAMESPACES)
                if r_fonts is not None:
                    ascii_font = r_fonts.attrib.get(f"{{{NAMESPACES['w']}}}ascii")
                    if ascii_font:
                        fonts.append(ascii_font)

        # Hyperlinks relationships
        hyperlink_urls: List[str] = []
        try:
            rels_content = zip_file.read("word/_rels/document.xml.rels")
            rels_root = ET.fromstring(rels_content)
            for rel in rels_root.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                if "hyperlink" in rel.attrib.get("Type", ""):
                    hyperlink_urls.append(rel.attrib.get("Target", ""))
        except KeyError:
            pass

        has_closure = any("Cordial e respeitosamente," in pt for pt in paragraphs_text)

    return DocxInspectionResult(
        page_width_twips=page_width,
        page_height_twips=page_height,
        page_orient=page_orient,
        margin_top_twips=m_top,
        margin_bottom_twips=m_bottom,
        margin_left_twips=m_left,
        margin_right_twips=m_right,
        line_spacings=line_spacings,
        justifications=justifications,
        fonts=list(set(fonts)),
        paragraphs_text=paragraphs_text,
        hyperlink_urls=hyperlink_urls,
        has_formal_closure=has_closure,
    )


# ==============================================================================
# Pytest Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def reference_cases() -> Dict[str, Dict[str, Any]]:
    """Returns the metadata mapping for all 9 reference cases."""
    if not HAS_REAL_CASES:
        pytest.skip("Real-world cases not present in environment (LGPD / clean repository)")
    return REFERENCE_CASES_METADATA


@pytest.fixture(scope="session")
def primary_case_metadata() -> Dict[str, Any]:
    """Returns metadata for the primary reference case 0801889-53.2023.8.20.5001."""
    if not HAS_REAL_CASES:
        pytest.skip("Real-world cases not present in environment (LGPD / clean repository)")
    return REFERENCE_CASES_METADATA["0801889-53.2023.8.20.5001"]


@pytest.fixture
def sample_summary_data() -> HearingSummaryData:
    """Returns a realistic, fully populated HearingSummaryData adhering to the canonical schema."""
    return HearingSummaryData(
        case_number="0801889-53.2023.8.20.5001",
        act_type="AIJ",
        hearing_datetime="31.07.26 às 10h00min",
        hearing_link="https://teams.microsoft.com/meet/284792802358140?p=MGiGbSP2E0MO1Jpl96",
        is_in_person=False,
        prosecutor="Dr. Jann Polacek Melo Cardoso",
        defendants=[
            Defendant(
                name="JUCIMARCIA SOARES DA SILVA",
                status="Ré respondendo ao processo em liberdade",
                citation_id="194381260",
                subpoena_id="194381260",
                qualification=(
                    "brasileira, solteira, diarista, natural de Natal/RN, "
                    "RG nº 1234567 - ITEP/RN, CPF nº 123.456.789-00, com 32 anos de idade, "
                    "filha de Maria Soares e Jose Soares, residente em Natal/RN, tel (84) 99999-9999"
                ),
            )
        ],
        defense_counsel="Defensoria Pública - Dr. Paulo Maycon",
        qualification_text=(
            "JUCIMARCIA SOARES DA SILVA, brasileira, solteira, diarista, natural de Natal/RN, "
            "RG nº 1234567 - ITEP/RN, CPF nº 123.456.789-00, residente em Natal/RN."
        ),
        imputation_text="Art. 129, § 9º, do Código Penal (Violência Doméstica).",
        facts_summary=(
            "Consta dos autos do inquérito policial que, no dia dos fatos, a denunciada "
            "ofendeu a integridade física de seu ex-companheiro. A materialidade foi comprovada "
            "pelo laudo pericial (ID 93845708)."
        ),
        chronological_history=[
            HistoryItem(
                date_str="10/06/23",
                description="Denúncia oferecida com proposta de Sursis processual",
                doc_id="101573748",
                pje_url="https://pje1g.tjrn.jus.br/pje/Processo/ConsultaProcesso/Detalhe/listProcessoCompleto.seam?id=101573748",
            ),
            HistoryItem(
                date_str="12/06/23",
                description="Decisão recebendo a denúncia",
                doc_id="101605793",
                pje_url="https://pje1g.tjrn.jus.br/pje/Processo/ConsultaProcesso/Detalhe/listProcessoCompleto.seam?id=101605793",
            ),
            HistoryItem(
                date_str="15/06/26",
                description="Decisão revogando o benefício e designando AIJ",
                doc_id="189952352",
                pje_url="https://pje1g.tjrn.jus.br/pje/Processo/ConsultaProcesso/Detalhe/listProcessoCompleto.seam?id=189952352",
            ),
        ],
        prosecution_witnesses=[
            Witness(
                number=1,
                name="Wallace Gomes Santos",
                role="Vítima",
                status_id="105732167",
            ),
            Witness(
                number=2,
                name="Allan Rychardson da Silva Cortes de Amorim",
                role="Policial Militar",
                status_id="191239678",
            ),
        ],
        defense_witnesses=[],
        defense_witness_note="A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia.",
        special_notes=None,
        closure_text="Cordial e respeitosamente,",
    )


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Returns an isolated temporary directory for test file generations."""
    out_dir = tmp_path / "test_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


@pytest.fixture
def network_blocker(monkeypatch: pytest.MonkeyPatch):
    """Guarantees strict zero-network execution by monkeypatching socket.connect."""
    def guarded_connect(self, *args, **kwargs):
        raise ConnectionRefusedError("Offline Mode Enforcement: Socket network calls are strictly prohibited.")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    return guarded_connect
