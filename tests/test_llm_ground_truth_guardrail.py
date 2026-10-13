"""Test suite for JEV / LAYA Ground-Truth & Citation Guardrail (UC-1).

Validates:
1. PJe Document ID verification and spurious ID eradication in history and witnesses.
2. Imputation penal audit preventing hallucination of non-existent articles.
3. Calendar and time boundary validation.
4. Automatic fallback to offline baseline when severe inconsistencies > 3.
5. Surgical sanitization when inconsistencies <= 3.

Desenvolvido por FChNeto.
"""

import pytest

from app.core.jev_decision_engine import JEVDecisionEngine
from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    PJeDocument,
    Witness,
)


@pytest.fixture
def sample_catalog():
    """Returns a realistic PJe document catalog."""
    return [
        PJeDocument(
            doc_id="101573748",
            date_str="10/02/2026 14:20",
            doc_name="Denúncia",
            doc_type="Denúncia",
            start_page=3,
            end_page=6,
        ),
        PJeDocument(
            doc_id="102485910",
            date_str="15/02/2026 10:15",
            doc_name="Decisão",
            doc_type="Decisão Interlocutória",
            start_page=7,
            end_page=8,
        ),
        PJeDocument(
            doc_id="105991823",
            date_str="20/02/2026 16:00",
            doc_name="Mandado de Intimação",
            doc_type="Mandado",
            start_page=9,
            end_page=10,
        ),
        PJeDocument(
            doc_id="108112233",
            date_str="25/02/2026 11:30",
            doc_name="Resposta à Acusação",
            doc_type="Petição",
            start_page=11,
            end_page=13,
        ),
    ]


@pytest.fixture
def sample_denuncia_text():
    return """
    EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA VARA CRIMINAL
    O MINISTÉRIO PÚBLICO DO ESTADO DO RIO GRANDE DO NORTE denuncia JOSÉ DA SILVA
    pela prática do crime previsto no art. 157, § 2º, II, c/c art. 14, II, ambos do Código Penal.
    Consta dos autos que o denunciado tentou subtrair mediante violência...
    """


@pytest.fixture
def baseline_offline_data():
    return HearingSummaryData(
        case_number="0801234-56.2026.8.20.5001",
        act_type="AIJ",
        hearing_datetime="15.03.26 às 10h00min",
        hearing_link="https://meet.google.com/xyz-abc",
        is_in_person=False,
        prosecutor="Dr. Promotor de Justiça",
        defendants=[
            Defendant(name="JOSÉ DA SILVA", status="Réu preso")
        ],
        defense_counsel="Defensoria Pública",
        qualification_text="JOSÉ DA SILVA, brasileiro, solteiro, RG 123456, CPF 000.111.222-33",
        imputation_text="art. 157, § 2º, II [roubo majorado] c/c art. 14, II [tentativa], do Código Penal",
        facts_summary="Consta que o acusado tentou subtrair bem mediante violência.",
        chronological_history=[
            HistoryItem(date_str="10/02/26", description="Denúncia oferecida pelo Ministério Público", doc_id="101573748"),
            HistoryItem(date_str="15/02/26", description="Decisão recebendo a denúncia", doc_id="102485910"),
        ],
        prosecution_witnesses=[
            Witness(number=1, name="Vítima João", role="Vítima", status_id="Intimado ID 105991823")
        ],
        defense_witnesses=[],
    )


def test_guardrail_preserves_legitimate_data(sample_catalog, sample_denuncia_text, baseline_offline_data):
    """When LLM output is 100% faithful and verified against the catalog, it passes without change."""
    jev = JEVDecisionEngine.get_instance()
    
    # LLM output identical to clean baseline
    audited = jev.audit_llm_ground_truth(
        llm_data=baseline_offline_data.model_copy(deep=True),
        pje_catalog=sample_catalog,
        denuncia_text=sample_denuncia_text,
        offline_fallback_data=baseline_offline_data,
    )

    assert audited.chronological_history[0].doc_id == "101573748"
    assert audited.chronological_history[1].doc_id == "102485910"
    assert "105991823" in audited.prosecution_witnesses[0].status_id
    assert "art. 157" in audited.imputation_text


def test_guardrail_eradicates_hallucinated_history_id(sample_catalog, sample_denuncia_text, baseline_offline_data):
    """Spurious history ID not present in PJe catalog must be stripped or remapped."""
    jev = JEVDecisionEngine.get_instance()

    corrupted_data = baseline_offline_data.model_copy(deep=True)
    # Add a history item with hallucinated ID
    corrupted_data.chronological_history.append(
        HistoryItem(date_str="18/02/26", description="Certidão de Publicação (ID 999999999)", doc_id="999999999")
    )

    audited = jev.audit_llm_ground_truth(
        llm_data=corrupted_data,
        pje_catalog=sample_catalog,
        denuncia_text=sample_denuncia_text,
        offline_fallback_data=baseline_offline_data,
    )

    # Fake ID must NOT appear anywhere in the audited item
    fake_item = audited.chronological_history[-1]
    assert fake_item.doc_id != "999999999"
    assert "999999999" not in fake_item.description


def test_guardrail_sanitizes_hallucinated_witness_id(sample_catalog, sample_denuncia_text, baseline_offline_data):
    """Hallucinated subpoena ID in witness list must be cleaned up."""
    jev = JEVDecisionEngine.get_instance()

    corrupted_data = baseline_offline_data.model_copy(deep=True)
    corrupted_data.prosecution_witnesses.append(
        Witness(number=2, name="PM Soldado Silva", role="PM", status_id="Intimado ID 888888888")
    )

    audited = jev.audit_llm_ground_truth(
        llm_data=corrupted_data,
        pje_catalog=sample_catalog,
        denuncia_text=sample_denuncia_text,
        offline_fallback_data=baseline_offline_data,
    )

    wit2 = audited.prosecution_witnesses[1]
    assert "888888888" not in (wit2.status_id or "")


def test_guardrail_detects_hallucinated_penal_article_and_restores(sample_catalog, sample_denuncia_text, baseline_offline_data):
    """When LLM hallucinates an extraneous penal article (e.g. art. 288 / associação criminosa), it is restored."""
    jev = JEVDecisionEngine.get_instance()

    corrupted_data = baseline_offline_data.model_copy(deep=True)
    # LLM hallucinates art. 288 which is NOT in the denuncia
    corrupted_data.imputation_text = "art. 157, § 2º, II c/c art. 288 [associação criminosa] do Código Penal"

    audited = jev.audit_llm_ground_truth(
        llm_data=corrupted_data,
        pje_catalog=sample_catalog,
        denuncia_text=sample_denuncia_text,
        offline_fallback_data=baseline_offline_data,
    )

    # Restores clean imputation
    assert "art. 288" not in audited.imputation_text
    assert "art. 157" in audited.imputation_text


def test_guardrail_corrects_invalid_calendar_datetime(sample_catalog, sample_denuncia_text, baseline_offline_data):
    """Absurd hearing dates (e.g. day 45, month 18) must be detected and restored."""
    jev = JEVDecisionEngine.get_instance()

    corrupted_data = baseline_offline_data.model_copy(deep=True)
    corrupted_data.hearing_datetime = "45.18.26 às 29h88min"

    audited = jev.audit_llm_ground_truth(
        llm_data=corrupted_data,
        pje_catalog=sample_catalog,
        denuncia_text=sample_denuncia_text,
        offline_fallback_data=baseline_offline_data,
    )

    assert audited.hearing_datetime == baseline_offline_data.hearing_datetime


def test_guardrail_triggers_full_fallback_on_exceeding_tolerance(sample_catalog, sample_denuncia_text, baseline_offline_data):
    """When LLM has > 3 severe inconsistencies, entire LLM response is discarded in favor of offline baseline."""
    jev = JEVDecisionEngine.get_instance()

    # Create heavily contaminated LLM response (> 3 severe errors)
    corrupted_data = baseline_offline_data.model_copy(deep=True)
    corrupted_data.facts_summary = "Fatos completamente alucinados pela IA"
    corrupted_data.chronological_history = [
        HistoryItem(date_str="01/01/26", description="Ato Fake 1", doc_id="111111111"),
        HistoryItem(date_str="02/01/26", description="Ato Fake 2", doc_id="222222222"),
    ]
    corrupted_data.prosecution_witnesses = [
        Witness(number=1, name="Testemunha Fake", role="PM", status_id="Intimado ID 333333333"),
        Witness(number=2, name="Outra Fake", role="PM", status_id="Intimado ID 444444444"),
    ]
    corrupted_data.imputation_text = "art. 121 [homicídio] c/c art. 333 [corrupção ativa] do Código Penal"

    audited = jev.audit_llm_ground_truth(
        llm_data=corrupted_data,
        pje_catalog=sample_catalog,
        denuncia_text=sample_denuncia_text,
        offline_fallback_data=baseline_offline_data,
    )

    # Full fallback triggered: facts_summary must be from baseline, not corrupted
    assert audited.facts_summary == baseline_offline_data.facts_summary
    assert audited.chronological_history[0].doc_id == "101573748"
    assert "Fatos completamente alucinados" not in audited.facts_summary
