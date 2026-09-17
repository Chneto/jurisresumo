"""Unit tests for Mode 1 (Gemini) and Mode 2 (Offline) extraction engines."""

import pytest
from pathlib import Path

from app.core.models import HearingSummaryData
from app.engines import get_engine, OfflineExtractionEngine, GeminiExtractionEngine


SAMPLE_PDF = Path("Proc. 0801889-53.2023.8.20.5001/Proc. 0801889-53.2023.8.20.5001.pdf")


def test_engine_factory():
    off = get_engine("offline")
    assert isinstance(off, OfflineExtractionEngine)

    gem = get_engine("gemini")
    assert isinstance(gem, GeminiExtractionEngine)


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="Sample PDF not present in environment")
def test_offline_engine_extraction():
    engine = OfflineExtractionEngine()
    result = engine.extract(str(SAMPLE_PDF))

    assert isinstance(result, HearingSummaryData)
    assert result.case_number == "0801889-53.2023.8.20.5001"
    assert result.act_type == "AIJ"
    assert len(result.defendants) >= 1
    assert "Jucimarcia" in result.defendants[0].name
    assert len(result.chronological_history) > 0
    assert result.closure_text == "Cordial e respeitosamente,"


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="Sample PDF not present in environment")
def test_gemini_engine_fallback_without_key():
    engine = GeminiExtractionEngine(api_key=None)
    # Should seamlessly fall back to offline engine without raising exceptions
    result = engine.extract(str(SAMPLE_PDF))

    assert isinstance(result, HearingSummaryData)
    assert result.case_number == "0801889-53.2023.8.20.5001"
    assert len(result.defendants) >= 1


def test_determine_act_type_aij_when_anpp_negated_or_denuncia_received():
    """Verify that mention of 'não persecução' or ANPP refusal in a case with received denúncia does NOT misclassify as ANPP."""
    engine = OfflineExtractionEngine()

    # Case 1: Judicial decision receives denúncia and schedules AIJ; cota mentioned ANPP refusal
    mock_hearing_text = "Vistos etc. Recebo a denúncia. Designo audiência de instrução e julgamento para a oitiva das testemunhas."
    act = engine._determine_act_type(
        hearing_text=mock_hearing_text,
        hearing_doc_name="Decisão - Designação de Audiência",
        filename="Proc. 0801234-56.2024.8.20.5001.pdf",
        denuncia_doc=object(),  # Denúncia exists
        pje_catalog=[],
        doc=[],
    )
    assert act == "AIJ"

    # Case 2: Explicit refusal of ANPP
    mock_refusal = "Deixo de propor acordo de não persecução penal tendo em vista a reincidência. Designo audiência de instrução."
    act2 = engine._determine_act_type(
        hearing_text=mock_refusal,
        hearing_doc_name="Despacho",
        filename="Processo.pdf",
        denuncia_doc=object(),
        pje_catalog=[],
        doc=[],
    )
    assert act2 == "AIJ"

    # Case 3: Genuine ANPP homologation hearing (no received denúncia)
    mock_anpp = "Designo audiência para fins do art. 28-A do CPP (homologação de ANPP)."
    act3 = engine._determine_act_type(
        hearing_text=mock_anpp,
        hearing_doc_name="Despacho - Homologação de Acordo",
        filename="Processo.pdf",
        denuncia_doc=None,
        pje_catalog=[],
        doc=[],
    )
    assert act3 == "ANPP"


def test_parse_datetime_portuguese_written_months():
    """Verify that dates written out in full Portuguese are parsed correctly."""
    engine = OfflineExtractionEngine()

    # Case 1: '24 de julho de 2026 às 11:25'
    dt1 = engine._parse_datetime_from_text("Designo o dia 24 de julho de 2026 às 11:25 para realização do ato.")
    assert dt1 == "24.07.26 às 11h25min"

    # Case 2: '31 de julho de 2026, às 10:00h'
    dt2 = engine._parse_datetime_from_text("Pauta para o dia 31 de julho de 2026, às 10:00h através do Teams.")
    assert dt2 == "31.07.26 às 10h00min"

    # Case 3: '15 de agosto de 2025 às 09:30'
    dt3 = engine._parse_datetime_from_text("audiência designada para 15 de agosto de 2025 às 09:30")
    assert dt3 == "15.08.25 às 09h30min"


def test_extract_facts_full_narrative_preservation():
    """Verify that facts from denúncia are preserved completely without arbitrary truncation."""
    engine = OfflineExtractionEngine()

    denuncia_sample = """
    I - DA QUALIFICAÇÃO
    FULANO DE TAL, brasileiro...

    II - DOS FATOS
    Consta nos inclusos autos do inquérito policial que, no dia 15 de janeiro de 2024, por volta das 21h,
    o denunciado subtraiu para si coisa alheia móvel pertencente à vítima.
    
    Ato contínuo, o denunciado empreendeu fuga em via pública, sendo perseguido por populares.
    
    A guarnição policial militar foi acionada e logrou êxito em deter o acusado em flagrante delito.

    III - DA IMPUTAÇÃO
    Como incurso nas penas do art. 155, caput, do Código Penal.
    """

    facts, notes = engine._extract_facts(
        denuncia_text=denuncia_sample,
        act_type="AIJ",
        pje_catalog=[],
        doc=[],
    )

    assert "Consta nos inclusos autos" in facts
    assert "empreendeu fuga em via pública" in facts
    assert "logrou êxito em deter o acusado" in facts

