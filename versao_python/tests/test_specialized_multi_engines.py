# -*- coding: utf-8 -*-
"""Unit and Integration Tests for Specialized Multi-Engine Architecture.

Tests all 10 domain engines and the Corroboration & Consensus Engine:
1. CapaPartiesEngine
2. HearingDetailsEngine
3. ClassificationHierarchyEngine
4. ProsecutorEngine
5. DefenseCounselEngine
6. DefendantQualificationEngine
7. ImputationTaxonomyEngine
8. FactsNarrativeEngine
9. ChronologicalHistoryEngine
10. WitnessSubpoenaEngine
11. CorroborationConsensusEngine

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import pytest
import pymupdf

from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    PJeDocument,
    Witness,
)
from app.engines.offline_engine import OfflineExtractionEngine
from app.engines.specialized import (
    CapaPartiesEngine,
    ChronologicalHistoryEngine,
    ClassificationHierarchyEngine,
    CorroborationConsensusEngine,
    DefendantQualificationEngine,
    DefenseCounselEngine,
    FactsNarrativeEngine,
    HearingDetailsEngine,
    ImputationTaxonomyEngine,
    ProsecutorEngine,
    WitnessSubpoenaEngine,
    ConsensusAuditReport,
)


# -----------------------------------------------------------------------------
# 1. CapaPartiesEngine Tests
# -----------------------------------------------------------------------------

def test_capa_parties_engine_case_number_and_filter():
    engine = CapaPartiesEngine()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "PROCESSO Nº 0801234-56.2026.8.20.5001\nPARTES DO PROCESSO\nJOÃO DA SILVA (REU)\nESTADO DO RIO GRANDE DO NORTE (REU)\nDR. ADVOGADO SANTOS (ADVOGADO)\nVARA CRIMINAL DE NATAL (REU)\nMARIA VÍTIMA (VÍTIMA)\nSD PM CARLOS (TESTEMUNHA)\nMINISTÉRIO PÚBLICO (AUTOR)\n7ª Promotoria de Justiça de Natal\nTABELA DE DOCUMENTOS")

    case_num = engine.extract_case_number(doc, "Proc. 0801234-56.2026.8.20.5001.pdf")
    assert case_num == "0801234-56.2026.8.20.5001"

    reus, advs, vitimas, testemunhas, prom = engine.parse_capa_parties(doc)
    assert "JOÃO DA SILVA" in reus
    assert "ESTADO DO RIO GRANDE DO NORTE" not in reus  # State organ discarded
    assert "VARA CRIMINAL DE NATAL" not in reus         # State organ discarded
    assert any("SANTOS" in a for a in advs)
    assert any("MARIA" in v for v in vitimas)
    assert any("CARLOS" in t for t in testemunhas)
    assert prom is not None and "7ª Promotoria" in prom
    doc.close()


# -----------------------------------------------------------------------------
# 2. HearingDetailsEngine Tests
# -----------------------------------------------------------------------------

def test_hearing_details_engine_datetime_and_links():
    engine = HearingDetailsEngine()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Designo audiência de instrução e julgamento para o dia 28 de outubro de 2026, às 14:30 horas.\nAcesse a sala virtual pelo link https://teams.microsoft.com/meet/987654321")

    p_doc = PJeDocument(
        doc_id="999",
        date_str="01/10/2026",
        doc_name="Despacho - Designação de Audiência",
        doc_type="Despacho",
        start_page=1,
        end_page=1,
    )
    catalog = [p_doc]

    found_doc, h_text = engine.find_hearing_document(catalog, doc)
    assert found_doc is not None
    assert found_doc.doc_id == "999"

    dt_str, link, is_in_person = engine.extract_hearing_details(
        hearing_text=h_text,
        filename="Proc. 0801234-56.2026.8.20.5001 - AIJ 28.10.26 às 14h30min.pdf",
        doc=doc,
        pje_catalog=catalog,
    )
    assert "28.10.26" in dt_str
    assert "14h30min" in dt_str
    assert link == "https://teams.microsoft.com/meet/987654321"
    assert is_in_person is False
    doc.close()


# -----------------------------------------------------------------------------
# 3. ClassificationHierarchyEngine Tests
# -----------------------------------------------------------------------------

def test_classification_hierarchy_engine_precedence():
    engine = ClassificationHierarchyEngine()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Vistos etc. Recebo a denúncia. Designo audiência de instrução e julgamento.")

    p_doc = PJeDocument(
        doc_id="111",
        date_str="10/05/2026",
        doc_name="Decisão - Recebimento",
        doc_type="Decisão",
        start_page=1,
        end_page=1,
    )
    catalog = [p_doc]
    denuncia_doc = PJeDocument(
        doc_id="100",
        date_str="01/05/2026",
        doc_name="Denúncia",
        doc_type="Denúncia",
        start_page=1,
        end_page=1,
    )

    act = engine.determine_act_type(
        filename="processo.pdf",
        hearing_text="recebo a denúncia e designo audiência de instrução",
        hearing_doc_name="Decisão",
        doc=doc,
        denuncia_doc=denuncia_doc,
        pje_catalog=catalog,
    )
    assert act == "AIJ"
    doc.close()


# -----------------------------------------------------------------------------
# 4. ProsecutorEngine Tests
# -----------------------------------------------------------------------------

def test_prosecutor_engine_digital_signature():
    engine = ProsecutorEngine()
    doc = pymupdf.open()
    denuncia_text = (
        "MINISTÉRIO PÚBLICO DO ESTADO DO RIO GRANDE DO NORTE\n"
        "Denúncia oferecida...\n\n"
        "Assinado eletronicamente por: MARCELO DA SILVA RAMOS - 15/03/2026"
    )
    prom_str = engine.extract_prosecutor(
        denuncia_text=denuncia_text,
        prom_capa="Dr. Promotor de Justiça (5ª Promotoria de Justiça)",
        doc=doc,
    )
    assert "Marcelo Da Silva Ramos" in prom_str
    assert "5ª Promotoria" in prom_str
    doc.close()


# -----------------------------------------------------------------------------
# 5. DefenseCounselEngine Tests
# -----------------------------------------------------------------------------

def test_defense_counsel_engine_private_and_defensoria():
    engine = DefenseCounselEngine()
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 50), "EXCELENTÍSSIMO JUIZ\nDefesa Prévia de MARCOS SILVA\nOAB/RN 12.345\nDr. Antonio Ferreira\npugna pela absolvição sumária.")

    p_doc = PJeDocument(
        doc_id="501",
        date_str="20/06/2026",
        doc_name="Resposta à Acusação",
        doc_type="Petição",
        start_page=1,
        end_page=1,
    )

    defense_docs = engine.find_all_defense_documents(
        pje_catalog=[p_doc],
        doc=doc,
        reus_capa=["MARCOS SILVA"],
        advs_capa=["ANTONIO FERREIRA"],
    )
    assert len(defense_docs) == 1
    assert defense_docs[0]["is_defensoria"] is False
    assert "Antonio Ferreira" in defense_docs[0]["lawyer_name"]
    assert "12.345" in defense_docs[0]["lawyer_oab"]

    counsel_str = engine.extract_defense_counsel(
        resposta_text=p1.get_text(),
        advs_capa=["ANTONIO FERREIRA"],
        doc=doc,
        defense_docs=defense_docs,
        reus_capa=["MARCOS SILVA"],
    )
    assert "advogado particular" in counsel_str.lower()
    assert "Antonio Ferreira" in counsel_str
    doc.close()


# -----------------------------------------------------------------------------
# 6. DefendantQualificationEngine Tests
# -----------------------------------------------------------------------------

def test_defendant_qualification_engine_multiline_and_ip_fallback():
    engine = DefendantQualificationEngine()
    doc = pymupdf.open()
    p_ip = doc.new_page()
    p_ip.insert_textbox(
        pymupdf.Rect(50, 50, 550, 750),
        "TERMO DE QUALIFICAÇÃO\nCARLOS EDUARDO PEREIRA, brasileiro, casado, filho de Tereza Pereira e João Pereira, RG 5.555.555 SSP/RN, CPF 111.222.333-44, residente na Rua do Sol, 45, Natal/RN."
    )

    ip_doc = PJeDocument(
        doc_id="202",
        date_str="05/01/2026",
        doc_name="Inquérito Policial",
        doc_type="Inquérito",
        start_page=1,
        end_page=1,
    )

    denuncia_omissa = "O Ministério Público oferece denúncia em face de CARLOS EDUARDO PEREIRA, qualificado no IP.\nDOS FATOS\nNo dia..."

    qual = engine.extract_single_defendant_qualification(
        name="CARLOS EDUARDO PEREIRA",
        raw_qual="",
        denuncia_text=denuncia_omissa,
        ip_text=p_ip.get_text(),
    )
    assert "CARLOS EDUARDO PEREIRA" in qual
    assert "Tereza Pereira" in qual or "filho de" in qual.lower()
    assert "111.222.333-44" in qual
    assert "Rua do Sol" in qual
    doc.close()


# -----------------------------------------------------------------------------
# 7. ImputationTaxonomyEngine Tests
# -----------------------------------------------------------------------------

def test_imputation_taxonomy_engine_special_laws_and_concurso():
    engine = ImputationTaxonomyEngine()
    denuncia_sample = (
        "Requer a condenação do réu como incurso nas penas do art. 157, § 2º, II, e § 2º-A, I, do Código Penal, "
        "c/c art. 244-B do ECA, na forma do art. 69 do Código Penal."
    )
    imp = engine.extract_imputation(denuncia_sample)
    assert "157" in imp
    assert "244-B" in imp or "ECA" in imp
    assert "69" in imp


# -----------------------------------------------------------------------------
# 8. FactsNarrativeEngine Tests
# -----------------------------------------------------------------------------

def test_facts_narrative_engine_boundary_stop():
    engine = FactsNarrativeEngine()
    denuncia_sample = (
        "Excelentíssimo Juiz de Direito da 1ª Vara Criminal.\n"
        "O Ministério Público vem oferecer denúncia:\n\n"
        "DOS FATOS\n"
        "No dia 12 de janeiro de 2026, por volta das 21h00min, o denunciado subtraiu o aparelho celular da vítima.\n"
        "Durante a fuga, foi contido por transeuntes até a chegada da polícia militar.\n\n"
        "ROL DE TESTEMUNHAS:\n"
        "1. Policial Militar José\n"
        "2. Vítima Ana\n"
        "Pede deferimento."
    )
    paras = engine.extract_clean_narrative(denuncia_sample)
    assert len(paras) >= 1
    assert "subtraiu o aparelho celular" in paras[0]
    assert not any("ROL DE TESTEMUNHAS" in p for p in paras)
    assert not any("Pede deferimento" in p for p in paras)
    assert not any("Excelentíssimo" in p for p in paras)


# -----------------------------------------------------------------------------
# 9. ChronologicalHistoryEngine Tests
# -----------------------------------------------------------------------------

def test_chronological_history_engine_act_summaries():
    engine = ChronologicalHistoryEngine()
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 50), "Vistos etc. Recebo a denúncia oferecida pelo MP. Cite-se o acusado.")

    p_doc = PJeDocument(
        doc_id="301",
        date_str="15/02/2026",
        doc_name="Decisão",
        doc_type="Decisão",
        start_page=1,
        end_page=1,
    )
    summary = engine.summarize_history_act(p_doc, doc)
    assert "Decisão recebendo a denúncia" in summary
    doc.close()


# -----------------------------------------------------------------------------
# 10. WitnessSubpoenaEngine Tests
# -----------------------------------------------------------------------------

def test_witness_subpoena_engine_deduplication_and_labeling():
    engine = WitnessSubpoenaEngine()
    doc = pymupdf.open()
    denuncia_sample = (
        "ROL DE TESTEMUNHAS:\n"
        "1. CB PM LUCAS OLIVEIRA (policial militar)\n"
        "2. MARIANA SANTOS (vítima)"
    )
    defense_docs = [
        {
            "doc_id": "701",
            "is_defensoria": True,
            "adopts_mp_witnesses": True,
            "explicit_witnesses": [],
            "represented_defendants": ["RÉU TESTE"],
        }
    ]

    pros_w, def_w, note = engine.extract_witnesses(
        denuncia_text=denuncia_sample,
        resposta_text="",
        vitimas_capa=[],
        testemunhas_capa=[],
        mandados_docs=[],
        doc=doc,
        defense_docs=defense_docs,
        reus_capa=["RÉU TESTE"],
    )
    assert len(pros_w) == 2
    assert "PM" in pros_w[0].role
    assert "vítima" in pros_w[1].role.lower()
    # Check unified adoption labeling
    assert "Defensoria Pública" in pros_w[0].role
    assert "Defensoria Pública" in pros_w[1].role
    doc.close()


# -----------------------------------------------------------------------------
# 11. CorroborationConsensusEngine Tests
# -----------------------------------------------------------------------------

def test_corroboration_consensus_engine_reconciliation():
    engine = CorroborationConsensusEngine()

    history = [
        HistoryItem(date_str="01/01/26", description="Denúncia oferecida", doc_id="101"),
        HistoryItem(date_str="05/01/26", description="Decisão revogando o Acordo de Não Persecução Penal (ANPP)", doc_id="102"),
    ]

    summary_data, audit = engine.reconcile_and_corroborate(
        case_number="0801234-56.2026.8.20.5001",
        act_type="ANPP",  # Incoherent initial act type
        hearing_datetime="10.11.26 às 10h00min",
        hearing_link=None,
        is_in_person=True,
        prosecutor="Dr. Promotor",
        defendants=[
            Defendant(name="JOÃO TESTE", status="respondendo em liberdade"),
            Defendant(name="DELEGACIA DE PLANTÃO", status="respondendo em liberdade"),  # Contaminant
        ],
        defense_counsel="",
        qualification_text="JOÃO TESTE, brasileiro...",
        imputation_text="art. 155 do CP",
        facts_summary="Fatos...",
        chronological_history=history,
        prosecution_witnesses=[
            Witness(number=1, name="TESTEMUNHA 1", role="Testemunha", status_id="Mandado expedido")
        ],
        defense_witnesses=[],
        defense_witness_note=None,
        special_notes=None,
        denuncia_text="art. 155 do CP",
        reus_capa=["JOÃO TESTE"],
        advs_capa=["DEFENSORIA PÚBLICA"],
        pje_catalog=[],
        defense_docs=[],
    )

    # Corroboration checks:
    # 1. Act type corrected to AIJ because ANPP was revoked in history
    assert summary_data.act_type == "AIJ"
    # 2. Contaminant state organ pruned
    assert len(summary_data.defendants) == 1
    assert summary_data.defendants[0].name == "JOÃO TESTE"
    # 3. Defense counsel defaulted to Defensoria Pública
    assert "Defensoria Pública" in summary_data.defense_counsel
    # 4. Audit report records actions
    assert isinstance(audit, ConsensusAuditReport)
    assert len(audit.adjustments_applied) > 0


# -----------------------------------------------------------------------------
# 12. OfflineExtractionEngine Multi-Engine Orchestrator End-to-End
# -----------------------------------------------------------------------------

def test_offline_extraction_engine_orchestration_instantiation():
    """Validates that OfflineExtractionEngine orchestrates all domain engines and records audit reports."""
    engine = OfflineExtractionEngine()
    assert isinstance(engine.capa_engine, CapaPartiesEngine)
    assert isinstance(engine.hearing_engine, HearingDetailsEngine)
    assert isinstance(engine.classification_engine, ClassificationHierarchyEngine)
    assert isinstance(engine.prosecutor_engine, ProsecutorEngine)
    assert isinstance(engine.defense_engine, DefenseCounselEngine)
    assert isinstance(engine.defendant_engine, DefendantQualificationEngine)
    assert isinstance(engine.imputation_engine, ImputationTaxonomyEngine)
    assert isinstance(engine.facts_engine, FactsNarrativeEngine)
    assert isinstance(engine.history_engine, ChronologicalHistoryEngine)
    assert isinstance(engine.witness_engine, WitnessSubpoenaEngine)
    assert isinstance(engine.corroboration_engine, CorroborationConsensusEngine)


# -----------------------------------------------------------------------------
# 13. Deep Cross-Verification and Robustness Tests
# -----------------------------------------------------------------------------

def test_corroboration_revocation_of_preventive_custody_stays_anpp():
    """Validates that revoking preventive detention does NOT incorrectly classify an ANPP case as AIJ."""
    engine = CorroborationConsensusEngine()
    history = [
        HistoryItem(date_str="01/02/26", description="Auto de Prisão em Flagrante", doc_id="101"),
        HistoryItem(date_str="05/02/26", description="Decisão revogando a prisão preventiva do acusado", doc_id="102"),
        HistoryItem(date_str="10/02/26", description="Despacho designando audiência de homologação de ANPP", doc_id="103"),
    ]
    report = ConsensusAuditReport()
    act, notes, facts = engine._corroborate_act_type(
        act_type="ANPP",
        chronological_history=history,
        special_notes=None,
        denuncia_text="",
        facts_summary="Trata-se de ANPP...",
        report=report,
    )
    assert act == "ANPP"
    assert "corrected from ANPP/SURSIS to AIJ" not in " ".join(report.adjustments_applied)


def test_corroboration_anpp_revocation_restores_aij_narrative_and_special_notes():
    """Validates that genuine revocation of ANPP sets act_type=AIJ, adds special_notes, and restores AIJ narrative."""
    engine = CorroborationConsensusEngine()
    history = [
        HistoryItem(date_str="01/01/26", description="Denúncia oferecida pelo Ministério Público", doc_id="101"),
        HistoryItem(date_str="05/01/26", description="Decisão revogando o Acordo de Não Persecução Penal (ANPP)", doc_id="555"),
        HistoryItem(date_str="10/01/26", description="Decisão designando audiência de instrução e julgamento", doc_id="556"),
    ]
    denuncia = (
        "DOS FATOS\n"
        "Consta dos inclusos autos que no dia 10 de janeiro de 2026, o denunciado furtou um veículo automotor.\n"
        "O denunciado foi preso em flagrante delito logo após a subtração.\n\n"
        "ROL DE TESTEMUNHAS:\n1. SD PM Ramos\nPede deferimento."
    )
    report = ConsensusAuditReport()
    act, notes, facts = engine._corroborate_act_type(
        act_type="ANPP",
        chronological_history=history,
        special_notes=None,
        denuncia_text=denuncia,
        facts_summary="Trata-se de ANPP em que o réu aceitou as condições...",
        report=report,
    )
    assert act == "AIJ"
    assert notes is not None and "revogou o Acordo de Não Persecução Penal (ANPP) (ID 555)" in notes
    assert "furtou um veículo automotor" in facts
    assert "Trata-se de ANPP" not in facts


def test_multi_defendant_independent_prison_status():
    """Validates that co-defendants have independent detention status (one detained, one free)."""
    engine = DefendantQualificationEngine()
    denuncia = (
        "DENUNCIADOS:\n"
        "1. JOÃO DA SILVA, brasileiro, atualmente preso na Cadeia Pública de Natal.\n"
        "2. PEDRO DOS SANTOS, brasileiro, residente na Rua do Sol, respondendo ao processo em liberdade.\n"
        "DOS FATOS\nNo dia..."
    )
    defs, qual = engine.extract_defendants_and_qual(
        denuncia_text=denuncia,
        reus_capa=["JOÃO DA SILVA", "PEDRO DOS SANTOS"],
        doc=None,
        pje_catalog=[],
        mandados_docs=[],
    )
    assert len(defs) == 2
    assert "preso" in defs[0].status.lower()
    assert "liberdade" in defs[1].status.lower()
    assert "preso" not in defs[1].status.lower()


def test_corroboration_reconciles_missing_defendant_from_capa_and_updates_qualification():
    """Validates that a defendant listed on Page 1 Capa but missed in body extraction is restored and synced into qualification."""
    engine = CorroborationConsensusEngine()
    report = ConsensusAuditReport()
    extracted_defs = [
        Defendant(name="JOÃO SILVA", status="respondendo em liberdade", qualification="JOÃO SILVA, brasileiro, solteiro.")
    ]
    reus_capa = ["JOÃO SILVA", "MARIA SOUZA"]

    reconciled_defs, reconciled_qual = engine._corroborate_defendants(
        defendants=extracted_defs,
        qualification_text="JOÃO SILVA, brasileiro, solteiro.",
        reus_capa=reus_capa,
        chronological_history=[],
        act_type="AIJ",
        report=report,
    )
    assert len(reconciled_defs) == 2
    names = [d.name.upper() for d in reconciled_defs]
    assert "JOÃO SILVA" in names
    assert "MARIA SOUZA" in names
    assert "MARIA SOUZA" in reconciled_qual.upper()
    assert report.defendants_reconciled == 2


def test_corroboration_prunes_witness_matching_defendant():
    """Validates that a defendant whose name accidentally appears in the witness list is pruned (anti-collision)."""
    engine = CorroborationConsensusEngine()
    report = ConsensusAuditReport()
    defs = [Defendant(name="CARLOS EDUARDO PEREIRA", status="respondendo em liberdade")]
    pros_w = [
        Witness(number=1, name="Sargento PM Alves", role="PM", status_id="Ofício enviado"),
        Witness(number=2, name="Carlos Eduardo Pereira", role="Testemunha", status_id="Intimado ID 111"),
        Witness(number=3, name="Mariana Vítima", role="vítima", status_id="Intimada ID 222"),
    ]
    cleaned_pros, cleaned_def, note = engine._corroborate_witnesses(
        prosecution_witnesses=pros_w,
        defense_witnesses=[],
        defense_witness_note=None,
        defense_docs=[],
        defendants=defs,
        report=report,
    )
    assert len(cleaned_pros) == 2
    assert not any("Carlos Eduardo Pereira" in w.name for w in cleaned_pros)
    assert cleaned_pros[0].number == 1
    assert cleaned_pros[1].number == 2
    assert any("Pruned defendant collision" in adj for adj in report.adjustments_applied)


def test_corroboration_unassigned_co_defendant_assigned_defensoria():
    """Validates that in multi-defendant cases, any unrepresented co-defendant is supplemented with Defensoria coverage."""
    engine = CorroborationConsensusEngine()
    report = ConsensusAuditReport()
    defs = [
        Defendant(name="ALICE SANTOS", status="respondendo em liberdade"),
        Defendant(name="BOB SILVA", status="respondendo em liberdade"),
    ]
    defense_docs = [
        {
            "is_defensoria": False,
            "lawyer_name": "Dr. Nelson",
            "lawyer_oab": "OAB/RN 111",
            "represented_defendants": ["Alice Santos"],
        }
    ]
    partial_counsel = "Dr. Nelson - OAB/RN 111 (em defesa de Alice Santos)"

    reconciled_counsel = engine._corroborate_defense_counsel(
        defense_counsel=partial_counsel,
        defendants=defs,
        defense_docs=defense_docs,
        advs_capa=["NELSON"],
        report=report,
    )
    assert "Dr. Nelson" in reconciled_counsel
    assert "Alice Santos" in reconciled_counsel
    assert "Defensoria Pública" in reconciled_counsel
    assert "Bob Silva" in reconciled_counsel


def test_corroboration_purges_procedural_articles_from_imputation():
    """Validates that non-penal procedural CPP and constitutional CF articles are purged from imputation."""
    engine = CorroborationConsensusEngine()
    report = ConsensusAuditReport()
    raw_imp = "art. 157, § 2º, II, do CP c/c art. 396 do CPP e art. 129, I da CF"

    qual, audited_imp = engine._corroborate_imputation(
        qualification_text="",
        imputation_text=raw_imp,
        denuncia_text="art. 157, § 2º, II, do CP",
        report=report,
    )
    assert "157" in audited_imp
    assert "396" not in audited_imp
    assert "129" not in audited_imp
    assert any("Purged non-penal procedural" in adj for adj in report.adjustments_applied)


def test_prosecutor_engine_unnumbered_promotoria():
    """Validates that comarca promotorias without ordinal numbers (e.g. Macaíba) are properly parsed."""
    engine = ProsecutorEngine()
    prom_str = engine.extract_prosecutor(
        denuncia_text="",
        prom_capa="Dr. Promotor de Justiça (Promotoria de Justiça de Macaíba)",
        doc=None,
    )
    assert "Promotoria de Justiça de Macaíba" in prom_str


def test_corroboration_recovers_hearing_datetime_from_history():
    """Validates that missing hearing datetime is recovered from chronological history designation act."""
    engine = CorroborationConsensusEngine()
    report = ConsensusAuditReport()
    history = [
        HistoryItem(
            date_str="01/03/26",
            description="Despacho incluindo o feito em pauta de audiência de instrução e julgamento para 18/06/2026, às 10h30min",
            doc_id="901",
        )
    ]
    recovered_dt = engine._corroborate_hearing_datetime(
        hearing_datetime="Data a definir",
        chronological_history=history,
        report=report,
    )
    assert "18.06.26" in recovered_dt
    assert "10h30min" in recovered_dt
    assert any("Recovered hearing datetime" in adj for adj in report.adjustments_applied)


def test_witness_subpoena_engine_exclusive_defense_witnesses_clears_def_note():
    """Validates that explicit defense witnesses clear def_note to None."""
    engine = WitnessSubpoenaEngine()
    defense_docs = [
        {
            "doc_id": "401",
            "is_defensoria": False,
            "lawyer_name": "Advogado Y",
            "adopts_mp_witnesses": False,
            "explicit_witnesses": ["Testemunha Exclusiva de Defesa 1"],
            "represented_defendants": ["Réu Z"],
        }
    ]
    pros_w, def_w, def_note = engine.extract_witnesses(
        denuncia_text="ROL DE TESTEMUNHAS:\n1. Soldado Silva (PM)",
        resposta_text="",
        vitimas_capa=[],
        testemunhas_capa=[],
        mandados_docs=[],
        doc=None,
        defense_docs=defense_docs,
        reus_capa=["Réu Z"],
    )
    assert len(pros_w) == 1
    assert len(def_w) == 1
    assert def_note is None

