"""Mode 1: Gemini AI Extraction Engine for Judicial Case Summaries.

Combines selective PJe document ingestion with Google Gemini structured output
to perform deep legal synthesis of criminal complaints, complex procedural acts,
and judicial hearings. Includes seamless fallback to Mode 2 (Offline Engine) if
no API key is configured.
"""

import json
import os
from pathlib import Path
from typing import List, Optional

import pymupdf

from app.core.models import HearingSummaryData, PJeDocument
from app.core.pje_indexer import index_pje_pdf, prune_documents
from app.engines.base import BaseExtractionEngine
from app.engines.offline_engine import OfflineExtractionEngine


GEMINI_EXTRACTION_SYSTEM_PROMPT = """Você é um Assessor Jurídico e Desenvolvedor Sênior especializado em Varas Criminais do TJRN (Tribunal de Justiça do Rio Grande do Norte) e processos eletrônicos no PJe.
Sua missão é extrair e sintetizar com rigor formal os autos do processo criminal para a confecção do RESUMO DE AUDIÊNCIA do Magistrado.

Regras Estritas de Estruturação Jurídica:
1. CABEÇALHO:
   - case_number: Número do processo formato CNJ (ex.: 0000000-00.2026.8.20.0000).
   - act_type: AIJ (Instrução e Julgamento), ANPP (Acordo de Não Persecução Penal) ou PAnP (Produção Antecipada de Provas).
   - hearing_datetime: Data e hora da audiência (ex.: "31.07.26 às 10h00min").
   - hearing_link: Link de reunião do Microsoft Teams ou Google Meet. Se for presencial ou inexistente, null.
   - is_in_person: true se for presencial, false se por videoconferência.
   - prosecutor: Nome do(a) Promotor(a) de Justiça com título Dr./Dra. e Promotoria (ex.: "Dr. Jann Polacek Melo Cardoso").
   - defendants: Lista de réus, com nome, situação prisional ("réu preso", "respondendo ao processo em liberdade", "foragido", etc.), e IDs de citação/intimação se disponíveis.
   - defense_counsel: "Assistido pela Defensoria Pública - Dr. [Nome]" ou "Representado por advogado particular, Dr. [Nome] - OAB/[UF] [Num]".

2. QUALIFICAÇÃO:
   - Exija 100% de literalidade da denúncia/autos. Transcreva a qualificação completa do(s) réu(s) sem qualquer truncamento ou omissão de atributos: Nome em caixa alta, nacionalidade, estado civil, profissão, nascimento/idade, naturalidade, filiação materna e paterna, RG com órgão/UF, CPF, endereço domiciliar e telefone. Vedada expressamente qualquer sumarização ou corte de dados qualificatórios. Se a denúncia for omissa, busque os dados no Inquérito Policial.

3. IMPUTAÇÃO:
   - Tipificação penal estritamente literal e completa abrangendo TODOS os artigos, parágrafos, incisos, alíneas, qualificadoras, causas de aumento, leis especiais (ECA, Drogas, Armamento, Maria da Penha, etc.) e concursos de crimes (arts. 69, 70 e 71 do CP) narrados na denúncia, sem simplificação ou truncamentos.

4. RESUMO DOS FATOS:
   - Geralmente (~99% das vezes) o resumo dos fatos é o que consta na narrativa da denúncia oferecida pelo Ministério Público.
   - Se a denúncia for excessivamente longa, faça um resumo objetivo preservando data, hora, local, dinâmica dos fatos, conduta de cada acusado, apreensão de bens/armas, exames periciais e declarações/confissões em sede policial.

5. HISTÓRICO PROCESSUAL:
   - Linha do tempo cronológica com formato estrito: DD/MM/AA: [Descrição do Ato/Decisão/Manifestação] (ID [número]).

6. TESTEMUNHAS:
   - Acusação e Defesa: nome, papel (Vítima, Policial Militar, Testemunha) e status de intimação/ofício com ID.

Retorne estritamente um objeto JSON válido compatível com o schema HearingSummaryData.
"""


class GeminiExtractionEngine(BaseExtractionEngine):
    """Mode 1: Hybrid Selective Ingestion + Google Gemini AI Extraction."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.offline_engine = OfflineExtractionEngine()

    def extract(
        self,
        pdf_path: str,
        pje_catalog: Optional[List[PJeDocument]] = None,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> HearingSummaryData:
        """Extracts summary data using Google Gemini AI, with offline fallback."""
        active_key = api_key or self.api_key or os.environ.get("GEMINI_API_KEY")

        # Fallback to Offline Engine if no Gemini API key provided
        if not active_key:
            return self.offline_engine.extract(pdf_path, pje_catalog=pje_catalog)

        try:
            # Import google-genai or fallback
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=active_key)

            # Ingest and prune key text from PJe PDF
            pdf_p = Path(pdf_path)
            if not pje_catalog:
                pje_catalog, doc = index_pje_pdf(pdf_path)
            else:
                doc = pymupdf.open(pdf_path)

            key_docs = prune_documents(pje_catalog)
            context_snippets = []

            # Add first 2 pages (TOC and Capa)
            for p in range(min(2, len(doc))):
                context_snippets.append(f"--- CAPA/TOC PÁGINA {p+1} ---\n{doc[p].get_text()}")

            # Add key judicial acts
            for k_doc in key_docs[:15]:
                if k_doc.start_page > 0:
                    text_parts = []
                    for p in range(k_doc.start_page - 1, min(k_doc.end_page, len(doc))):
                        text_parts.append(doc[p].get_text())
                    doc_content = "\n".join(text_parts)[:4000]
                    context_snippets.append(
                        f"--- DOCUMENTO: {k_doc.doc_name} (Tipo: {k_doc.doc_type}, ID: {k_doc.doc_id}, Data: {k_doc.date_str}) ---\n{doc_content}"
                    )

            doc.close()
            full_context = "\n\n".join(context_snippets)

            # Call Gemini with structured response schema
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    GEMINI_EXTRACTION_SYSTEM_PROMPT,
                    f"Abaixo estão os documentos extraídos dos autos do processo ({pdf_p.name}):\n\n{full_context}",
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=HearingSummaryData,
                    temperature=0.1,
                ),
            )

            result_dict = json.loads(response.text)
            return HearingSummaryData.model_validate(result_dict)

        except Exception as err:
            # If any Gemini API or quota error occurs, fallback seamlessly to offline engine
            return self.offline_engine.extract(pdf_path, pje_catalog=pje_catalog)
