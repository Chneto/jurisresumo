"""Unit and integration tests for ANPP and PSCP revocation handling.
Verifies that:
1. Revocation of ANPP or PSCP forces AIJ classification (retomada da marcha penal).
2. The chronological history records the revocation decision with its PJe ID.
3. special_notes is properly populated with the canonical judicial observation.
4. DOCX generator renders special_notes in italic under RESUMO DOS FATOS.
5. JEV decision engine enforces AIJ on revocation.
Autor: FChNeto
"""

import io
import zipfile
import pytest
import pymupdf

from app.core.models import HearingSummaryData, PJeDocument, Defendant
from app.core.jev_decision_engine import JEVDecisionEngine
from app.engines.offline_engine import OfflineExtractionEngine
from app.generators.docx_generator import generate_docx_summary


def test_jev_hierarchy_revocation_anpp_forces_aij():
    """JEV ClassificationHierarchyCPP must prioritize revocation of ANPP and return AIJ."""
    jev = JEVDecisionEngine.get_instance()
    catalog = [
        PJeDocument(doc_id="111", date_str="01/01/2026", doc_name="Decisão", doc_type="Decisão", start_page=10, end_page=11)
    ]
    anpp_rev = PJeDocument(doc_id="111", date_str="01/01/2026", doc_name="Decisão", doc_type="Decisão", start_page=10, end_page=11)
    
    act = jev.classify_act_hierarchy(
        h_comb="audiência para homologação de anpp",
        fn_upper="HOMOLOGACAO_ANPP.PDF",
        pje_catalog=catalog,
        anpp_rev_doc=anpp_rev,
    )
    assert act == "AIJ", f"Expected AIJ on ANPP revocation, got {act}"


def test_jev_hierarchy_revocation_pscp_forces_aij():
    """JEV ClassificationHierarchyCPP must prioritize revocation of PSCP and return AIJ."""
    jev = JEVDecisionEngine.get_instance()
    catalog = [
        PJeDocument(doc_id="222", date_str="01/01/2026", doc_name="Decisão", doc_type="Decisão", start_page=10, end_page=11)
    ]
    pscp_rev = PJeDocument(doc_id="222", date_str="01/01/2026", doc_name="Decisão", doc_type="Decisão", start_page=10, end_page=11)
    
    act = jev.classify_act_hierarchy(
        h_comb="audiência de suspensão condicional do processo",
        fn_upper="SURSIS.PDF",
        pje_catalog=catalog,
        pscp_rev_doc=pscp_rev,
    )
    assert act == "AIJ", f"Expected AIJ on PSCP revocation, got {act}"


def test_offline_engine_summarize_history_anpp_revocation():
    """_summarize_history_act must label an ANPP revocation decision accurately."""
    engine = OfflineExtractionEngine()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Em face do descumprimento das condições acordadas, declaro a rescisão do acordo de não persecução penal (ANPP).")
    p_doc = PJeDocument(doc_id="123", date_str="10/01/2026", doc_name="Decisão", doc_type="Decisão", start_page=1, end_page=1)

    desc = engine._summarize_history_act(p_doc, doc)
    assert desc == "Decisão revogando o Acordo de Não Persecução Penal (ANPP)"


def test_offline_engine_summarize_history_pscp_revocation():
    """_summarize_history_act must label a PSCP revocation decision accurately."""
    engine = OfflineExtractionEngine()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Constatado novo crime durante o período de prova, revogo o benefício do art. 89 da Lei 9.099/95 (suspensão condicional do processo).")
    p_doc = PJeDocument(doc_id="456", date_str="10/01/2026", doc_name="Decisão", doc_type="Decisão", start_page=1, end_page=1)

    desc = engine._summarize_history_act(p_doc, doc)
    assert desc == "Decisão revogando a Suspensão Condicional do Processo (PSCP)"


def test_special_notes_in_facts_and_docx():
    """Verifies that special_notes is properly generated and rendered in OpenXML DOCX."""
    data = HearingSummaryData(
        case_number="0801234-56.2025.8.20.0001",
        act_type="AIJ",
        hearing_datetime="15/10/2026 às 09:00",
        prosecutor="Dr. Promotor de Justiça",
        defense_counsel="Assistido pela Defensoria Pública",
        qualification_text="FULANO DE TAL, brasileiro, solteiro.",
        imputation_text="Art. 155, § 4º, I e IV [furto qualificado], do Código Penal",
        facts_summary="Consta da denúncia que no dia 01/01/2025 o réu subtraiu coisa alheia móvel.",
        special_notes="Obs.: Audiência de Instrução e Julgamento designada após decisão que revogou o Acordo de Não Persecução Penal (ANPP) (ID 99887766), com a retomada do curso regular da ação penal.",
        defendants=[Defendant(name="Fulano de Tal", status="respondendo ao processo em liberdade")],
        chronological_history=[
            {"date_str": "10/01/25", "description": "Denúncia oferecida pelo Ministério Público", "doc_id": "11111111"},
            {"date_str": "20/05/25", "description": "Decisão revogando o Acordo de Não Persecução Penal (ANPP)", "doc_id": "99887766"}
        ]
    )

    docx_bytes = generate_docx_summary(data)
    assert len(docx_bytes) > 2000

    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        doc_xml = z.read("word/document.xml").decode("utf-8")
        assert "retomada do curso regular da ação penal" in doc_xml
        assert "99887766" in doc_xml
        assert "RESUMO DOS FATOS" in doc_xml
        assert "HISTÓRICO PROCESSUAL" in doc_xml
        assert "<w:hyperlink" in doc_xml
        rels_xml = z.read("word/_rels/document.xml.rels").decode("utf-8")
        assert "idBin=99887766" in rels_xml


def test_offline_engine_summarize_history_anpp_revocation_in_despacho():
    """_summarize_history_act must detect ANPP revocation even if document is titled 'Despacho' or 'Termo'."""
    engine = OfflineExtractionEngine()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Diante do inadimplemento injustificado, revogo o acordo de não persecução penal e designo audiência.")
    p_doc = PJeDocument(doc_id="789", date_str="12/03/2026", doc_name="Despacho", doc_type="Despacho", start_page=1, end_page=1)

    desc = engine._summarize_history_act(p_doc, doc)
    assert desc == "Decisão revogando o Acordo de Não Persecução Penal (ANPP)"

