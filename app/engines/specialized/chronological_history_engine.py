# -*- coding: utf-8 -*-
"""Specialized Engine 9: Chronological Procedural History Engine (ChronologicalHistoryEngine).

Responsible for:
1. Selecting and pruning procedural acts from the PJe catalog.
2. Generating substantive, faithful legal descriptions of judicial acts.
3. Incorporating synthesized defense responses and decisions revoking ANPP/PSCP.
4. Formatting dates strictly as DD/MM/AA.
5. Ascending chronological sorting based on parsed date and document ID.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Optional
import pymupdf

from app.core.models import HistoryItem, PJeDocument
from app.core.ocr_engine import OCREngine
from app.core.pje_indexer import prune_documents
from app.engines.specialized.common import (
    ANPP_REVOCATION_REGEX,
    PSCP_REVOCATION_REGEX,
    _format_date_short,
    _parse_date_sort_key,
    extract_doc_text,
)


class ChronologicalHistoryEngine:
    """Specialized engine for chronological history generation, act summarization, and date ordering."""

    def build_chronological_history(
        self,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
        reus_capa: Optional[List[str]] = None,
        advs_capa: Optional[List[str]] = None,
        defense_docs: Optional[List[Dict]] = None,
    ) -> List[HistoryItem]:
        """Constructs the comprehensive chronological procedural history with IDs and substantive summaries."""
        if reus_capa is None:
            reus_capa = []
        if advs_capa is None:
            advs_capa = []

        items: List[HistoryItem] = []
        seen_ids = set()

        # 1. Map defense responses (named and inominada)
        defense_docs_map: Dict[str, Dict] = {}
        if defense_docs is None:
            from app.engines.specialized.defense_counsel_engine import DefenseCounselEngine
            defense_docs = DefenseCounselEngine().find_all_defense_documents(pje_catalog, doc, reus_capa, advs_capa)

        for d_info in defense_docs:
            defense_docs_map[d_info["doc_id"]] = d_info

        key_docs = prune_documents(pje_catalog)
        # Ensure any identified defense document is included in key_docs if not already present
        key_doc_ids = {d.doc_id for d in key_docs}
        for d_info in defense_docs:
            if d_info["doc_id"] not in key_doc_ids:
                key_docs.append(d_info["doc"])
                key_doc_ids.add(d_info["doc_id"])

        # Ensure any decision revoking ANPP or PSCP is included in key_docs
        if doc is not None:
            for p_doc in pje_catalog:
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["decis", "despacho", "ato ordinat", "termo"]):
                    txt = extract_doc_text(doc, p_doc)
                    if ANPP_REVOCATION_REGEX.search(txt) or PSCP_REVOCATION_REGEX.search(txt):
                        if p_doc.doc_id not in key_doc_ids:
                            key_docs.append(p_doc)
                            key_doc_ids.add(p_doc.doc_id)

        for p_doc in key_docs:
            if p_doc.doc_id in seen_ids or p_doc.start_page == 0:
                continue
            seen_ids.add(p_doc.doc_id)

            short_date = _format_date_short(p_doc.date_str)
            if p_doc.doc_id in defense_docs_map:
                description = defense_docs_map[p_doc.doc_id]["summary_for_history"]
            else:
                description = self.summarize_history_act(p_doc, doc)

            items.append(
                HistoryItem(
                    date_str=short_date,
                    description=description,
                    doc_id=p_doc.doc_id,
                )
            )

        # Sort strictly in ascending chronological order:
        items.sort(key=lambda it: _parse_date_sort_key(it.date_str, it.doc_id))
        return items

    def summarize_history_act(self, p_doc: PJeDocument, doc: pymupdf.Document) -> str:
        """Generates a substantive, meaningful legal summary for a procedural document."""
        raw_name = p_doc.doc_name.strip()
        raw_name = re.sub(r"^\d+\s*-\s*", "", raw_name)
        type_l = p_doc.doc_type.lower()
        name_l = raw_name.lower()

        # Extract page text with calibrated OCR fallback for scanned pieces
        txt = ""
        if doc is not None and len(doc) > 0:
            for p in range(p_doc.start_page - 1, min(p_doc.end_page, len(doc))):
                p_txt = doc[p].get_text()
                if not p_txt.strip() or (p_doc.is_scanned and len(p_txt.strip()) < 50):
                    ocr_res = OCREngine.get_instance().ocr_page(doc[p])
                    if ocr_res and ocr_res.text.strip():
                        p_txt = ocr_res.text
                txt += p_txt + "\n"

        txt_l = txt.lower()

        # 1. Denúncia / Queixa-Crime / Petição Inicial
        if "denúncia" in name_l or "denuncia" in name_l:
            if "não foi proposto anpp" in txt_l or "deixo de propor anpp" in txt_l:
                return "Denúncia. Consta cota afirmando que não foi proposto ANPP em face dos denunciados"
            elif "suspensão condicional" in txt_l or "sursis" in txt_l:
                return "Denúncia oferecida com proposta de Suspensão Condicional do Processo"
            return "Denúncia oferecida pelo Ministério Público"

        if "petição inicial" in name_l or "peticao inicial" in name_l:
            if "queixa" in txt_l or "querelante" in txt_l or "querelada" in txt_l:
                return "Queixa-crime oferecida pelo querelante"
            return "Petição inicial protocolada"

        # 2. Revogação de ANPP ou PSCP em qualquer ato judicial decisório (Decisão, Despacho, Termo, Ata)
        has_anpp_rev = bool(ANPP_REVOCATION_REGEX.search(txt_l))
        has_pscp_rev = bool(PSCP_REVOCATION_REGEX.search(txt_l) or ("revoga" in txt_l and ("suspensão" in txt_l or "sursis" in txt_l)))

        if any(k in name_l for k in ["decis", "despacho", "termo", "ata", "ato ordinat"]):
            if has_anpp_rev and has_pscp_rev:
                return "Decisão revogando o Acordo de Não Persecução Penal (ANPP) e a Suspensão Condicional do Processo (PSCP)"
            if has_anpp_rev:
                return "Decisão revogando o Acordo de Não Persecução Penal (ANPP)"
            if has_pscp_rev:
                return "Decisão revogando a Suspensão Condicional do Processo (PSCP)"

        # 3. Decisão
        if "decisão" in name_l or "decisao" in name_l:
            if "recebo a denúncia" in txt_l or "recebida a denúncia" in txt_l or "recebimento da denúncia" in txt_l:
                if "pauta" in txt_l or "designo" in txt_l:
                    return "Decisão recebendo a denúncia e designando audiência"
                return "Decisão recebendo a denúncia"
            if "produção antecipada" in txt_l or "art. 366" in txt_l:
                return "Decisão suspendendo o processo (art. 366 CPP) e designando produção antecipada de provas"
            if "pauta" in txt_l or "designo" in txt_l or "instrução" in txt_l:
                return "Decisão designando audiência de instrução e julgamento"
            return "Decisão interlocutória"

        # 4. Despacho
        if "despacho" in name_l:
            if "conciliação" in txt_l or "conciliacao" in txt_l:
                dt_m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})[^\n\d]{1,20}(\d{1,2}:\d{2}|\d{1,2}h\d{0,2})", txt)
                if dt_m:
                    return f"Despacho incluindo o feito em pauta de audiência de conciliação para {dt_m.group(1)}, às {dt_m.group(2)}"
                return "Despacho incluindo o feito em pauta de audiência de conciliação"
            if "pauta" in txt_l or "designo" in txt_l or "instrução" in txt_l:
                dt_m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})[^\n\d]{1,20}(\d{1,2}:\d{2}|\d{1,2}h\d{0,2})", txt)
                if dt_m:
                    return f"Despacho incluindo o feito em pauta de audiência de instrução e julgamento para {dt_m.group(1)}, às {dt_m.group(2)}"
                return "Despacho incluindo o feito em pauta de audiência de instrução e julgamento"
            if "reaprazo" in txt_l or "redesigno" in txt_l:
                return "Despacho redesignando a audiência"
            if "homologação de anpp" in txt_l or "homologar" in txt_l:
                return "Despacho designando audiência de homologação de ANPP"
            if "admissibilidade" in txt_l or "requisitos" in txt_l:
                return "Despacho para análise de admissibilidade da queixa-crime"
            if "aguarde-se o inquérito" in txt_l or "aguarde-se o inqu" in txt_l:
                return "Despacho tomando ciência do APF e determinando aguardo do inquérito policial"
            return "Despacho judicial"

        # 5. Resposta à acusação / Defesa prévia
        if "resposta" in name_l or "defesa prévia" in name_l or "defesa previa" in name_l:
            return "Resposta à acusação pugnando pela absolvição sumária do acusado"

        # 6. Manifestação / Devolução de inquérito
        if any(k in name_l for k in ["manifesta", "promo", "cota", "devolu"]):
            if "devolu" in name_l or "devolu" in txt_l:
                m_dp = re.search(r"(\d+ª?\s*DP[^\n,;.]+)", txt, re.I)
                dp_str = f" à {m_dp.group(1).strip()}" if m_dp else ""
                if "dilig" in txt_l or "dilig" in name_l:
                    return f"Manifestação ministerial devolvendo os autos{dp_str} para realização de diligências"
                return f"Manifestação ministerial devolvendo os autos{dp_str}"
            if "laudo" in txt_l and "pericial" in txt_l:
                return "Manifestação ministerial requerendo juntada de Laudo Pericial"
            if "cota" in txt_l or "denúncia" in txt_l:
                return "Manifestação ministerial (cota da denúncia)"
            return "Manifestação ministerial"

        # 7. APF e Inquérito Policial
        if "apf" in name_l:
            m_apf = re.search(r"APF\s+(\d+/\d+)", raw_name, re.I)
            if m_apf:
                return f"Auto de Prisão em Flagrante (APF {m_apf.group(1)})"
            return "Auto de Prisão em Flagrante (APF)"

        if "inquérito" in name_l or "inquerito" in name_l or re.search(r"\bip\s+\d+/\d+", name_l):
            m_ip = re.search(r"IP\s+(\d+/\d+)", raw_name, re.I)
            if m_ip:
                return f"Inquérito Policial (IP {m_ip.group(1)})"
            return "Inquérito Policial"

        # 8. Alvará de Soltura
        if "alvará de soltura" in name_l or "alvara de soltura" in name_l:
            clean = re.sub(r"_\d+$", "", raw_name).replace("_", " ")
            clean = re.sub(r"^alvar[aá]\s+de\s+soltura\s*", "", clean, flags=re.I).strip()
            if clean:
                return f"Alvará de soltura expedido em favor de {clean.title()}"
            return "Alvará de soltura expedido"

        # 9. Link de Audiência
        if "link" in name_l and "audi" in name_l:
            return "Expedição de link de acesso para a audiência"

        # 10. Devolução de Mandado / Certidões
        if "devolução de mandado" in name_l or ("certidão" in name_l and "mandado" in name_l):
            if any(k in txt_l for k in ["contrafé negativa", "contrafe negativa", "não localizado", "deixei de citar", "deixei de intimar"]):
                return "Certidão do Oficial de Justiça - contrafé negativa (não localizado)"
            if "alvará" in txt_l or "alvara" in txt_l:
                return "Certidão de cumprimento de alvará de soltura"
            if any(k in txt_l for k in ["positivo", "cumprido", "citei", "intimei"]):
                return "Certidão do Oficial de Justiça informando cumprimento de mandado"
            return "Certidão do Oficial de Justiça devolvendo mandado"

        # 11. Citação / Edital / Mandados / Atos Ordinatórios
        if "edital" in name_l:
            return "Citação por edital do acusado"
        if "mandado" in name_l and "citação" in name_l:
            return "Mandado de citação"
        if "mandado" in name_l and "intimação" in name_l:
            return "Mandado de intimação de audiência"
        if "intimação de audiência" in name_l or "intimação de audiência" in type_l or "mandado de intimação audiência" in txt_l:
            return "Intimação de audiência expedida"

        if "ato ordinat" in name_l or ("intima" in name_l and "audi" not in name_l):
            if any(k in txt_l for k in ["vistas ao mp", "abro vistas", "vistas ao ministério"]):
                return "Ato ordinatório abrindo vistas ao Ministério Público"
            if "autoridade policial" in txt_l and "tramitação direta" in txt_l:
                return "Intimação da Autoridade Policial para diligências (tramitação direta)"
            if "ministério público" in txt_l and "tramitação direta" in txt_l:
                return "Intimação do Ministério Público (tramitação direta)"
            if "intima" in name_l:
                return "Intimação expedida"

        # 12. Audiências anteriores / Atas
        if "ata da audiência" in name_l or "termo de audiência" in name_l:
            if "custódia" in txt_l:
                return "Audiência de Custódia realizada"
            if "suspensão" in txt_l or "sursis" in txt_l:
                return "Audiência de Suspensão Condicional do Processo realizada"
            if "instrução" in txt_l:
                return "Ata de audiência de instrução realizada"
            return "Ata da audiência"

        # Clean trailing system IDs or hashes from fallback name
        cleaned_fallback = re.sub(r"_\d{10,}$", "", raw_name)
        cleaned_fallback = re.sub(r"\.pdf$", "", cleaned_fallback, flags=re.I).strip(" _-")
        return cleaned_fallback
