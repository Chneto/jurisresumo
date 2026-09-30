# -*- coding: utf-8 -*-
"""Suíte de Testes para Extração Rígida e Literal de Qualificação e Imputação Penal.

Valida:
1. Extração multilinha de qualificação com filiação, RG, CPF e endereço domiciliar.
2. Fallback de qualificação no Inquérito Policial (IP/APF) se a denúncia for omissa ("qualificado no IP").
3. Captura ampla e completa de múltiplos artigos, parágrafos, incisos, leis especiais (ECA) e concursos de crimes.
4. Auditoria e complementação automática via JEVDecisionEngine.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"

import pytest
from app.core.jev_decision_engine import JEVDecisionEngine
from app.engines.offline_engine import OfflineExtractionEngine


def test_multiline_qualification_extraction():
    """Testa se a qualificação multilinha é capturada integralmente sem cortes em ';' ou '\\n'."""
    engine = OfflineExtractionEngine()
    denuncia_sample = (
        "MINISTÉRIO PÚBLICO DO ESTADO DO RIO GRANDE DO NORTE\n"
        "O Ministério Público oferece denúncia contra:\n\n"
        "JOÃO DA SILVA, brasileiro, solteiro, pedreiro, nascido em 10/05/1990, natural de Natal/RN,\n"
        "filho de Maria da Silva e José da Silva, portador do RG nº 1.234.567 ITEP/RN e inscrito no CPF nº 123.456.789-00,\n"
        "residente e domiciliado na Rua das Flores, nº 100, Bairro Petrópolis, Natal/RN, tel. (84) 99999-8888;\n\n"
        "DOS FATOS\n"
        "No dia 15 de janeiro de 2026..."
    )

    qual = engine._extract_single_defendant_qualification(
        name="JOÃO DA SILVA",
        raw_qual="",
        denuncia_text=denuncia_sample,
        ip_text="",
    )

    assert "JOÃO DA SILVA" in qual
    assert "Maria da Silva" in qual or "filho de" in qual.lower()
    assert "1.234.567" in qual
    assert "123.456.789-00" in qual
    assert "Rua das Flores" in qual


def test_qualification_fallback_on_inquerito_policial():
    """Testa se denúncia omissa ('qualificado às fls. X do IP') aciona o fallback no IP/APF."""
    engine = OfflineExtractionEngine()
    denuncia_omissa = (
        "O MINISTÉRIO PÚBLICO oferece denúncia contra SEBASTIÃO SOUZA, já qualificado às fls. 05 do IP.\n"
        "DOS FATOS\n"
        "No dia 10 de fevereiro de 2026..."
    )
    ip_sample = (
        "TERMO DE QUALIFICAÇÃO E INTERROGATÓRIO\n"
        "Aos 02/02/2026, compareceu SEBASTIÃO SOUZA, brasileiro, casado, mecânico, nascido em 20/08/1985,\n"
        "filho de Francisca Souza e Antonio Souza, RG nº 987654 SSP/RN, CPF nº 987.654.321-11, residente na Av. Brasil, 50."
    )

    qual = engine._extract_single_defendant_qualification(
        name="SEBASTIÃO SOUZA",
        raw_qual="",
        denuncia_text=denuncia_omissa,
        ip_text=ip_sample,
    )

    assert "SEBASTIÃO SOUZA" in qual
    assert "Francisca Souza" in qual or "filho de" in qual.lower()
    assert "987654" in qual
    assert "987.654.321-11" in qual


def test_imputation_multiple_articles_and_special_laws():
    """Testa a extração de imputação com múltiplos artigos, ECA (art. 244-B) e concurso material (art. 69 CP)."""
    engine = OfflineExtractionEngine()
    denuncia_text = (
        "O Ministério Público pugna pela condenação do réu como incurso nas sanções do artigo 157, § 2º, II, do Código Penal,\n"
        "c/c artigo 244-B da Lei nº 8.069/90 (ECA), ambos na forma do artigo 69 do Código Penal."
    )

    imputation = engine._extract_imputation(denuncia_text)

    assert "157" in imputation
    assert "244-B" in imputation
    assert "69" in imputation or "CP" in imputation


def test_jev_decision_engine_audits_qualification_and_imputation():
    """Testa a auditoria determinística do JEV Decision Engine complementando a qualificação e imputação."""
    jev = JEVDecisionEngine.get_instance()

    raw_qual = "MARCOS ALVES, brasileiro, solteiro, residente em Natal/RN."
    raw_imp = "Art. 157, § 2º, II, do Código Penal."
    denuncia = (
        "Denuncio MARCOS ALVES como incurso no art. 157, § 2º, II, c/c art. 244-B do ECA e art. 69 do CP. "
        "Filho de Tereza Alves, RG nº 554433 ITEP/RN, CPF nº 555.444.333-22."
    )

    audited_qual, audited_imp = jev.audit_qualification_and_imputation(
        qualification_text=raw_qual,
        imputation_text=raw_imp,
        denuncia_text=denuncia,
        ip_text="",
    )

    assert "Tereza Alves" in audited_qual or "filho de" in audited_qual.lower()
    assert "554433" in audited_qual
    assert "555.444.333-22" in audited_qual

    assert "244-B" in audited_imp
    assert "69" in audited_imp
