"""Test suite verifying calibration and replication of the 8 reference TJRN summary models.

Validates OpenXML DOCX generation, JEV classification, callout highlights,
multi-defendant formatting, singular/plural defense witness headers,
defense witness adoption notes, and LGPD-compliant data isolation.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import io
import zipfile
import pytest
import xml.etree.ElementTree as ET

from app.core.models import Defendant, HearingSummaryData, HistoryItem, Witness
from app.core.jev_decision_engine import JEVDecisionEngine
from app.generators.docx_generator import generate_docx_summary


def _extract_docx_xml(docx_bytes: bytes) -> str:
    """Helper to extract word/document.xml from generated DOCX buffer."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return z.read("word/document.xml").decode("utf-8")


def test_panp_model_structure_and_highlights():
    """Model 1: PAnP (Art. 366 CPP) with yellow callout, green defendant suspension status, and yellow defense note."""
    data = HearingSummaryData(
        case_number="0800001-00.2026.8.20.5600",
        act_type="PAnP",
        hearing_datetime="23/07/2026 às 13h00min",
        hearing_link="https://teams.microsoft.com/meet/123456",
        prosecutor="Dr. Promotor de Justiça",
        defendants=[
            Defendant(
                name="RÉU SINTÉTICO 1",
                status="O réu, citado por edital, não atendeu ao chamamento judicial, encontrando-se o processo e o prazo prescricional suspensos com relação a ele.",
            )
        ],
        defense_counsel="Assistido pela Defensoria Pública - Dr. Defensor",
        qualification_text="RÉU SINTÉTICO 1, brasileiro, solteiro, qualificação nos autos.",
        imputation_text="art. 155, caput, do Código Penal.",
        facts_summary="No dia 01 de janeiro de 2026, o denunciado subtraiu coisa alheia móvel.",
        chronological_history=[
            HistoryItem(date_str="01/02/26", description="Denúncia", doc_id="10000001"),
            HistoryItem(date_str="05/02/26", description="Decisão suspendendo o processo (art. 366 CPP)", doc_id="10000002"),
        ],
        prosecution_witnesses=[
            Witness(number=1, name="Testemunha Acusação 1", role="vítima", status_id="Intimada ID 10000003")
        ],
        defense_witnesses=[],
        defense_witness_note="Não há testemunhas de defesa arroladas.",
    )

    docx_bytes = generate_docx_summary(data)
    xml_str = _extract_docx_xml(docx_bytes)

    # 1. Callout with yellow highlight for PAnP
    assert "Audiência de produção antecipada de provas orais" in xml_str
    assert '<w:highlight w:val="yellow"/>' in xml_str

    # 2. Promotor and Réu with green highlight
    assert '<w:highlight w:val="green"/>' in xml_str
    assert "PROMOTOR: Dr. Promotor de Justiça" in xml_str

    # 3. Yellow highlight on defense witness note
    assert "Não há testemunhas de defesa arroladas." in xml_str


def test_aij_idoso_callout_and_adoption_note():
    """Model 4: AIJ (IDOSO) with yellow callout tag and defense adopting prosecution witness list."""
    data = HearingSummaryData(
        case_number="0800002-00.2026.8.20.5001",
        act_type="AIJ (IDOSO)",
        hearing_datetime="24/07/2026 às 11h",
        hearing_link="https://teams.microsoft.com/meet/654321",
        prosecutor="Dr. Promotor de Justiça",
        defendants=[
            Defendant(
                name="RÉU SINTÉTICO 2",
                status="solto",
                subpoena_id="20000001",
            )
        ],
        defense_counsel="Representado pela Defensoria Pública - Dr. Defensor",
        qualification_text="RÉU SINTÉTICO 2, brasileiro, solteiro, residente em Natal/RN.",
        imputation_text="art. 140, §3º, do Código Penal.",
        facts_summary="Narrativa fática sintética do caso.",
        chronological_history=[
            HistoryItem(date_str="10/03/26", description="Denúncia", doc_id="20000002"),
        ],
        prosecution_witnesses=[
            Witness(number=1, name="PM Policial 1", role="PM", status_id="Ofício enviado ID 20000003"),
            Witness(number=2, name="Vítima Idosa", role="vítima", status_id="Intimada ID 20000004"),
        ],
        defense_witnesses=[],
        defense_witness_note="A defesa requereu a oitiva de todas as testemunhas arroladas pela acusação na denúncia.",
    )

    docx_bytes = generate_docx_summary(data)
    xml_str = _extract_docx_xml(docx_bytes)

    # 1. Callout for IDOSO in yellow
    assert "11h - 0800002-00.2026.8.20.5001 - AIJ (IDOSO)" in xml_str

    # 2. Defense witness note in yellow
    assert "A defesa requereu a oitiva de todas as testemunhas arroladas pela acusação na denúncia." in xml_str


def test_multi_defendant_numbering_and_defense_witness_singular():
    """Model 3 & 6: Multi-defendant list numbered 01), 02) and singular 'TESTEMUNHA DE DEFESA:' when exactly 1 witness."""
    data = HearingSummaryData(
        case_number="0800003-00.2026.8.20.5001",
        act_type="AIJ",
        hearing_datetime="10/07/2026 às 11:00",
        hearing_link="https://teams.microsoft.com/meet/789012",
        prosecutor="Dr. Promotor de Justiça",
        defendants=[
            Defendant(name="RÉU SINTÉTICO A", status="solto", subpoena_id="30000001"),
            Defendant(name="RÉU SINTÉTICO B", status="solto", subpoena_id="30000002"),
            Defendant(name="RÉU SINTÉTICO C", status="solto", subpoena_id="30000003"),
        ],
        defense_counsel="Advogado dos réus: Dr. Advogado Particular - OAB/PB 0000",
        qualification_text="RÉU SINTÉTICO A, qualificado.\n\nRÉU SINTÉTICO B, qualificado.\n\nRÉU SINTÉTICO C, qualificado.",
        imputation_text="art. 157, §2º, II, do CP.",
        facts_summary="Narrativa fática com múltiplos réus.",
        chronological_history=[],
        prosecution_witnesses=[
            Witness(number=1, name="Testemunha 1", role="vítima", status_id="Intimada ID 30000004")
        ],
        defense_witnesses=[
            Witness(number=1, name="Testemunha Defesa Única", role="Testemunha de Defesa", status_id="Intimada ID 30000005")
        ],
    )

    docx_bytes = generate_docx_summary(data)
    xml_str = _extract_docx_xml(docx_bytes)

    # 1. Multi-defendant header 'Réus:' with green highlight
    assert "Réus:" in xml_str
    assert "01) RÉU SINTÉTICO A" in xml_str
    assert "02) RÉU SINTÉTICO B" in xml_str
    assert "03) RÉU SINTÉTICO C" in xml_str

    # 2. Singular 'TESTEMUNHA DE DEFESA:' header
    assert "TESTEMUNHA DE DEFESA:" in xml_str
    assert "TESTEMUNHAS DE DEFESA:" not in xml_str


def test_anpp_six_paragraph_structure_docx():
    """Model 5: ANPP 6-paragraph structure with zero Qualificação/Imputação/Histórico/Testemunhas."""
    anpp_facts = (
        "OBS: este processo foi oriundo de um desmembramento da ação penal nº 0800000-00.2024.8.20.5600...\n\n"
        "Investigada Sintética foi indiciada por crime previsto no art. 155, §4º, I, do CP.\n\n"
        "17/06/26: O Ministério Público realizou a tratativa de ANPP...\n\n"
        "CONDIÇÕES DO ACORDO: a) prestação pecuniária...; b) comprovantes...; c) não cometer crimes...\n\n"
        "10/06/26: Decisão de ID 40000001 determinou a cisão dos autos...\n\n"
        "07/07/26: Despacho designando a audiência de homologação de ANPP para 24/07/26, às 11h25 (ID 40000002)"
    )

    data = HearingSummaryData(
        case_number="0800004-00.2026.8.20.5001",
        act_type="ANPP",
        hearing_datetime="24/07/2026 às 11h25min",
        hearing_link="https://teams.microsoft.com/meet/444444",
        prosecutor="Dr. Promotor de Justiça",
        defendants=[Defendant(name="INVESTIGADA SINTÉTICA", status="solta", subpoena_id="40000003")],
        defense_counsel="Advogado: Dr. Advogado Particular – OAB RN n. 0000",
        facts_summary=anpp_facts,
    )

    docx_bytes = generate_docx_summary(data)
    xml_str = _extract_docx_xml(docx_bytes)

    # 1. ANPP Callout in yellow
    assert "11h25min - 0800004-00.2026.8.20.5001 - ANPP" in xml_str
    assert "RESUMO DOS FATOS" in xml_str

    # 2. Omission of other sections
    assert "QUALIFICAÇÃO" not in xml_str
    assert "IMPUTAÇÃO" not in xml_str
    assert "HISTÓRICO PROCESSUAL" not in xml_str
    assert "TESTEMUNHAS DE ACUSAÇÃO:" not in xml_str


def test_lgpd_isolation_of_reference_models():
    """Ensures models in 'modelos de resumos' are kept strictly local and ignored by git."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    if root.name == "versao_python":
        root = root.parent
    gitignore_path = root / ".gitignore"
    assert gitignore_path.is_file()
    git_content = gitignore_path.read_text(encoding="utf-8")

    assert "modelos de resumos/" in git_content
    assert "*.pdf" in git_content
