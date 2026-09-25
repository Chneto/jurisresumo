"""Test suite for OCR Engine calibration and JEV / Leya decision engine.

Validates noise filtering, bank slip rejection, dynamic margins, confidence scoring,
and System One classification of procedural documents.

Desenvolvido por FChNeto.
"""

import io
import pytest
import pymupdf
from PIL import Image, ImageDraw

from app.core.jev_decision_engine import JEVDecisionEngine
from app.core.models import DocumentCategory, OCRLine
from app.core.ocr_engine import OCREngine, is_scanned_page


def test_jev_singleton():
    """JEVDecisionEngine should provide a working singleton accessor."""
    jev1 = JEVDecisionEngine.get_instance()
    jev2 = JEVDecisionEngine.get_instance()
    assert jev1 is jev2


def test_jev_rejects_banking_noise():
    """JEV engine should immediately classify bank vouchers and payment slips as RUIDO_IRRELEVANTE."""
    jev = JEVDecisionEngine.get_instance()

    banking_text = """
    BANCO DO BRASIL - SEGUNDA VIA
    COMPROVANTE DE PAGAMENTO DE GUIA DE CUSTAS
    AUTENTICAÇÃO MECÂNICA: 1234.5678.9012.3456
    LINHA DIGITÁVEL: 00190.00009 01234.567890 12345.678901 1 89010000015000
    VALOR TOTAL R$ 150,00
    """
    res = jev.classify_text_block(banking_text, doc_title="Comprovante", doc_type="Comprovante de Pagamento")
    assert res.category == DocumentCategory.RUIDO_IRRELEVANTE
    assert res.relevance_score <= 0.20
    assert not res.is_essential


def test_jev_rejects_admin_certidao():
    """JEV engine should reject generic administrative certificates."""
    jev = JEVDecisionEngine.get_instance()

    certidao_text = """
    CERTIDÃO DE JUNTADA GENÉRICA
    Certifico que decorreu o prazo sem manifestação da parte ré.
    Faço conclusos estes autos ao MM. Juiz de Direito.
    """
    res = jev.classify_text_block(certidao_text, doc_title="Certidão", doc_type="Certidão de Triagem")
    assert res.category == DocumentCategory.RUIDO_IRRELEVANTE
    assert res.relevance_score < 0.40
    assert not res.is_essential


def test_jev_classifies_denuncia():
    """JEV engine should recognize prosecution charging documents with high score."""
    jev = JEVDecisionEngine.get_instance()

    denuncia_text = """
    EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA 1ª VARA CRIMINAL
    O MINISTÉRIO PÚBLICO DO ESTADO DO RIO GRANDE DO NORTE, por intermédio do Promotor de Justiça,
    vem oferecer DENÚNCIA em face de JOSÉ DA SILVA, qualificado nos autos.
    Consta dos inclusos autos de inquérito policial que, no dia 15 de maio de 2026, por volta das 21h30min,
    o denunciado, agindo livre e conscientemente, subtraiu mediante grave ameaça com arma de fogo a quantia de R$ 500,00 da vítima.
    A materialidade e autoria restaram demonstradas pelo laudo pericial e termo de exibição e apreensão.
    Diante do exposto, o Ministério Público denuncia o acusado como incurso nas penas do art. 157, § 2º, II do Código Penal.
    """
    res = jev.classify_text_block(denuncia_text, doc_title="Denúncia", doc_type="Denúncia")
    assert res.category == DocumentCategory.DENUNCIA_FATOS
    assert res.relevance_score >= 0.70
    assert res.is_essential


def test_jev_classifies_decisao_aij():
    """JEV engine should classify hearing scheduling decisions as DECISAO_AIJ."""
    jev = JEVDecisionEngine.get_instance()

    decisao_text = """
    DECISÃO
    Recebo a denúncia oferecida em desfavor do réu.
    Não sendo caso de absolvição sumária, designo o dia 25 de novembro de 2026, às 14h30min,
    para a realização da audiência de instrução e julgamento (AIJ).
    Intimem-se as testemunhas e requisite-se o réu preso.
    """
    res = jev.classify_text_block(decisao_text, doc_title="Decisão", doc_type="Decisão Interlocutória")
    assert res.category == DocumentCategory.DECISAO_AIJ
    assert res.relevance_score >= 0.85
    assert res.is_essential


def test_jev_classifies_panp():
    """JEV engine should classify Art. 366 CPP decisions as DECISAO_PANP."""
    jev = JEVDecisionEngine.get_instance()

    panp_text = """
    DECISÃO
    O acusado foi citado por edital e não compareceu.
    Suspendo o processo e o curso do prazo prescricional, com fulcro no art. 366 do CPP.
    Considerando a urgência na oitiva dos policiais militares, designo audiência de produção antecipada de provas.
    """
    res = jev.classify_text_block(panp_text, doc_title="Decisão de Suspensão", doc_type="Decisão")
    assert res.category == DocumentCategory.DECISAO_PANP
    assert res.is_essential


def test_jev_filter_noise_lines():
    """Line filtering should strip PJe marginal stamps and OCR garbage."""
    jev = JEVDecisionEngine.get_instance()

    raw_lines = [
        "Num. 12345678 - Pág. 12",
        "Assinado eletronicamente por: FULANO DE TAL",
        "https://pje1g.tjrn.jus.br/consultapublica/Processo/ConsultaProcesso/detalhe.seam",
        "...",
        "-",
        "No dia 10 de maio de 2026, o acusado desferiu golpes na vítima.",
        "AUTENTICAÇÃO MECÂNICA 987654321",
        "A materialidade está comprovada pelo laudo pericial (ID 12345).",
    ]

    cleaned = jev.filter_noise_lines(raw_lines)
    assert len(cleaned) == 2
    assert "No dia 10 de maio" in cleaned[0]
    assert "A materialidade está comprovada" in cleaned[1]


def test_ocr_engine_singleton():
    """OCREngine should provide singleton instance."""
    ocr1 = OCREngine.get_instance()
    ocr2 = OCREngine.get_instance()
    assert ocr1 is ocr2
    assert ocr1.is_available


def test_ocr_preprocessing():
    """Image preprocessing should increase contrast and sharpen without altering dimensions."""
    ocr = OCREngine.get_instance()

    img = Image.new("RGB", (200, 100), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "TESTE JURISRESUMO", fill=(50, 50, 50))

    preproc = ocr.preprocess_image(img, enhance_contrast=True, autocontrast=True, sharpen=True)
    assert preproc.size == (200, 100)
    assert preproc.mode == "L"


def test_is_scanned_page_detection():
    """is_scanned_page should distinguish empty/image pages from native text pages."""
    doc = pymupdf.open()
    # Page 1: Native vector text
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 150), "Este é um texto vetorial longo suficiente para ser classificado como nativo no PJe.")

    # Page 2: Empty page
    doc.new_page(width=595, height=842)

    assert not is_scanned_page(doc[0])
    assert is_scanned_page(doc[1])
    doc.close()
