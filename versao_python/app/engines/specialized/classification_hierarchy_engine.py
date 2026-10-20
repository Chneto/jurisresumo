# -*- coding: utf-8 -*-
"""Specialized Engine 2: Procedural Classification Hierarchy Engine (ClassificationHierarchyEngine).

Responsible for:
1. Determining the exact legal act type following criminal procedure hierarchy:
   JÚRI -> CUSTÓDIA -> JUSTIFICAÇÃO / PROTETIVA -> ANPP -> AIJ -> PAnP -> SURSIS.
2. Detecting judicial decisions receiving the accusatory complaint (recebimento da denúncia).
3. Detecting ministerial refusals or judicial rejections of ANPP (ANPP negation).
4. Detecting decisions revoking ANPP or PSCP (art. 89 Lei 9.099/95), which resume standard AIJ proceedings.
5. Delegating to the canonical JEV / Leya decision engine.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

from typing import List, Optional
import pymupdf

from app.core.models import PJeDocument
from app.core.jev_decision_engine import JEVDecisionEngine
from app.engines.specialized.common import (
    ANPP_NEGATION_REGEX,
    ANPP_REVOCATION_REGEX,
    PSCP_REVOCATION_REGEX,
    extract_doc_text,
)


class ClassificationHierarchyEngine:
    """Specialized engine for criminal procedure hierarchy classification."""

    def determine_act_type(
        self,
        filename: str,
        hearing_text: str,
        hearing_doc_name: str,
        doc: pymupdf.Document,
        denuncia_doc: Optional[PJeDocument],
        pje_catalog: List[PJeDocument],
        anpp_rev_doc: Optional[PJeDocument] = None,
        pscp_rev_doc: Optional[PJeDocument] = None,
    ) -> str:
        """Determines the exact legal act type following criminal procedure hierarchy:

        1. PAnP: Produção Antecipada de Provas (Art. 366 CPP).
        2. ANPP: Acordo de Não Persecução Penal (Art. 28-A CPP) when scheduled hearing is affirmatively for homologation.
        3. AIJ: Standard oral hearing in criminal actions (receipt of denúncia, witness inquiry, interrogatório).
        4. Custódia: Auto de Prisão em Flagrante (APF) prior to complaint filing.
        5. Sursis: Hearing for conditional suspension of proceedings (Art. 89 Lei 9.099/95).
        """
        fn_upper = filename.upper()
        h_comb = f"{hearing_doc_name} {hearing_text}".lower()

        # Scan catalog and pages to check if denúncia was offered/received or ANPP rejected
        has_denuncia = denuncia_doc is not None
        has_received_denuncia = False
        has_aij_mention = False
        has_anpp_rejection = False

        if pje_catalog and doc is not None:
            for p_doc in pje_catalog:
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["decis", "despacho", "ato ordinat", "termo", "audiência"]):
                    txt = extract_doc_text(doc, p_doc).lower()
                    if "recebo a denúncia" in txt or "recebida a denúncia" in txt or "recebimento da denúncia" in txt or "art. 396" in txt or "art. 399" in txt or "absolvição sumária" in txt:
                        has_received_denuncia = True
                    if "instrução e julgamento" in txt or "audiência de instrução" in txt or "oitiva de testemunha" in txt or "oitiva das testemunhas" in txt or "inquirir as testemunhas" in txt or "interrogatório do réu" in txt:
                        has_aij_mention = True
                    if ANPP_NEGATION_REGEX.search(txt) or "não sendo caso de anpp" in txt or "afasto o anpp" in txt or "recusa do anpp" in txt or "anpp recusado" in txt or "deixo de propor anpp" in txt:
                        has_anpp_rejection = True

        # Check for revocation documents in catalog if not explicitly provided
        if pje_catalog and doc is not None:
            for p_doc in pje_catalog:
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["decis", "despacho", "ato ordinat", "termo"]):
                    txt = extract_doc_text(doc, p_doc)
                    if not anpp_rev_doc and ANPP_REVOCATION_REGEX.search(txt):
                        anpp_rev_doc = p_doc
                    if not pscp_rev_doc and PSCP_REVOCATION_REGEX.search(txt):
                        pscp_rev_doc = p_doc

        # Delegate directly to canonical JEV Classification Hierarchy
        return JEVDecisionEngine.get_instance().classify_act_hierarchy(
            h_comb=h_comb,
            fn_upper=fn_upper,
            pje_catalog=pje_catalog or [],
            anpp_rev_doc=anpp_rev_doc,
            pscp_rev_doc=pscp_rev_doc,
            has_received_denuncia=has_received_denuncia,
            has_aij_mention=has_aij_mention,
            has_anpp_rejection=has_anpp_rejection,
            has_denuncia=has_denuncia,
        )
