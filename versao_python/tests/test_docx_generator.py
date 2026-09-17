"""Unit tests for the high-fidelity DOCX generator."""

import io
import zipfile
import xml.etree.ElementTree as ET
import pytest
from docx import Document

from app.core.models import Defendant, HearingSummaryData, HistoryItem, Witness
from app.generators.docx_generator import generate_docx_summary
from tests.conftest import NAMESPACES


@pytest.fixture
def sample_hearing_data() -> HearingSummaryData:
    return HearingSummaryData(
        case_number="0801889-53.2023.8.20.5001",
        act_type="AIJ",
        hearing_datetime="31.07.26 às 10h00min",
        hearing_link="https://teams.microsoft.com/meet/284792802358140?p=MGiGbSP2E0MO1Jpl96",
        prosecutor="Dr. Jann Polacek Melo Cardoso",
        defendants=[
            Defendant(
                name="Jucimarcia Soares da Silva",
                status="Ré respondendo ao processo em liberdade",
                subpoena_id="194381260",
            )
        ],
        defense_counsel="Assistida pela Defensoria Pública - Dr. Paulo Maycon",
        qualification_text="JUCIMARCIA SOARES DA SILVA, brasileira, em união estável, vendedora...",
        imputation_text="Lesão corporal em situação de relação doméstica (art. 129, §9º, do Código Penal)",
        facts_summary="Consta nos referidos autos do inquérito policial que...",
        chronological_history=[
            HistoryItem(
                date_str="10/06/23",
                description="Denúncia oferecida pelo Ministério Público",
                doc_id="101573748",
            ),
            HistoryItem(
                date_str="12/06/23",
                description="Decisão recebendo a denúncia",
                doc_id="101605793",
            ),
        ],
        prosecution_witnesses=[
            Witness(
                number=1,
                name="Wallace Gomes Santos",
                role="vítima",
                status_id="Certidão contrafé negativa ID 193523731",
            ),
            Witness(
                number=2,
                name="Allan Rychardson da Silva Cortes de Amorim",
                role="PM",
                status_id="Ofício enviado ID 191239678",
            ),
        ],
        defense_witness_note="A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia.",
        closure_text="Cordial e respeitosamente,",
    )


def test_docx_page_setup(sample_hearing_data):
    docx_bytes = generate_docx_summary(sample_hearing_data)
    doc = Document(io.BytesIO(docx_bytes))
    section = doc.sections[0]

    # Verify A4 dimensions (within 0.1 cm)
    assert abs(section.page_width.cm - 21.0) < 0.1
    assert abs(section.page_height.cm - 29.7) < 0.1

    # Verify 2.0 cm margins
    assert abs(section.top_margin.cm - 2.0) < 0.1
    assert abs(section.bottom_margin.cm - 2.0) < 0.1
    assert abs(section.left_margin.cm - 2.0) < 0.1
    assert abs(section.right_margin.cm - 2.0) < 0.1


def test_docx_typography_and_elements(sample_hearing_data):
    docx_bytes = generate_docx_summary(sample_hearing_data)
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        tree = ET.fromstring(z.read("word/document.xml"))

    # Verify font family Verdana
    rFonts = tree.findall(".//w:rFonts", NAMESPACES)
    assert len(rFonts) > 0
    assert any(rf.attrib.get(f"{{{NAMESPACES['w']}}}ascii") == "Verdana" for rf in rFonts)

    # Verify presence of hyperlinks
    hyperlinks = tree.findall(".//w:hyperlink", NAMESPACES)
    assert len(hyperlinks) >= 3  # Teams link + at least 2 IDs

    # Verify formal closure text
    text_content = "".join(t.text for t in tree.findall(".//w:t", NAMESPACES) if t.text)
    assert "Cordial e respeitosamente," in text_content
    assert "0801889-53.2023.8.20.5001" in text_content
    assert "Jucimarcia Soares da Silva" in text_content
    assert "101573748" in text_content


def test_docx_highlights_strict(sample_hearing_data):
    """Ensures presence of yellow and green highlights matching judge's reference models."""
    docx_bytes = generate_docx_summary(sample_hearing_data)
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        tree = ET.fromstring(z.read("word/document.xml"))

    highlights = [
        hl.attrib.get(f"{{{NAMESPACES['w']}}}val")
        for hl in tree.findall(".//w:highlight", NAMESPACES)
    ]
    assert "yellow" in highlights, "Yellow highlight must be present on section headers and notes"
    assert "green" in highlights, "Green highlight must be present on hearing participants"

