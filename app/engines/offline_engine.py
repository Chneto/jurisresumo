# -*- coding: utf-8 -*-
"""Mode 2: 100% Offline Local Multi-Engine System for Judicial Case Summaries.

Orchestrates 10 specialized domain engines with mutual cross-corroboration and consensus
guardrails to parse complete PJe PDF files without external network connections.

Engines:
1. CapaPartiesEngine: Case number and Page 1 Capa parties ingestion.
2. HearingDetailsEngine: Designation act identification, datetime parsing, and link detection.
3. ClassificationHierarchyEngine: Criminal procedure hierarchy classification (CPP).
4. ProsecutorEngine: Prosecuting magistrate identification and promotoria styling.
5. DefenseCounselEngine: Defense representation, petitions parsing, and attorney mapping.
6. DefendantQualificationEngine: Multiline qualification, IP fallback, and citation status.
7. ImputationTaxonomyEngine: Penal charge extraction and statutory taxonomy annotation.
8. FactsNarrativeEngine: Factual narrative extraction, boundary enforcement, and ANPP synthesis.
9. ChronologicalHistoryEngine: Procedural history reconstruction and substantive act summaries.
10. WitnessSubpoenaEngine: Witness rol extraction, subpoena linking, and unified deduplication.
11. CorroborationConsensusEngine: Multi-engine cross-verification and consensus reconciliation.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pymupdf

from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    PJeDocument,
    Witness,
)
from app.core.pje_indexer import index_pje_pdf, prune_documents
from app.engines.base import BaseExtractionEngine

# Re-export all common helpers, regexes, and constants for full backward compatibility
from app.engines.specialized.common import (
    ANPP_NEGATION_REGEX,
    ANPP_REVOCATION_REGEX,
    CNJ_REGEX,
    HEARING_DESIGNATION_REGEX,
    MEET_REGEX,
    MONTH_MAP,
    PSCP_REVOCATION_REGEX,
    STATE_ORGANS_BLACKLIST_REGEX,
    TEAMS_REGEX,
    _clean_legal_text,
    _format_date_short,
    _make_accent_tolerant_regex,
    _normalize_witness_name,
    _parse_date_sort_key,
    extract_doc_text,
)

# Import the specialized multi-engine agents
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


class OfflineExtractionEngine(BaseExtractionEngine):
    """100% Offline Multi-Engine Orchestrator for PJe judicial case autos."""

    def __init__(self):
        """Initializes all specialized engines."""
        self.capa_engine = CapaPartiesEngine()
        self.hearing_engine = HearingDetailsEngine()
        self.classification_engine = ClassificationHierarchyEngine()
        self.prosecutor_engine = ProsecutorEngine()
        self.defense_engine = DefenseCounselEngine()
        self.defendant_engine = DefendantQualificationEngine()
        self.imputation_engine = ImputationTaxonomyEngine()
        self.facts_engine = FactsNarrativeEngine()
        self.history_engine = ChronologicalHistoryEngine()
        self.witness_engine = WitnessSubpoenaEngine()
        self.corroboration_engine = CorroborationConsensusEngine()

    def extract(
        self,
        pdf_path: str,
        pje_catalog: Optional[List[PJeDocument]] = None,
        **kwargs,
    ) -> HearingSummaryData:
        """Extracts structured summary data locally from the PJe PDF via the multi-engine system."""
        pdf_p = Path(pdf_path)
        if not pdf_p.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Index PJe PDF if catalog not provided
        if not pje_catalog:
            pje_catalog, doc = index_pje_pdf(pdf_path)
        else:
            doc = pymupdf.open(pdf_path)

        # 1. Engine 1: Extract Case Number and Capa Parties
        case_number = self.capa_engine.extract_case_number(doc, pdf_p.name)
        reus_capa, advs_capa, vitimas_capa, testemunhas_capa, prom_capa = self.capa_engine.parse_capa_parties(doc)

        # 2. Locate Key Documents
        matching_denuncias: List[PJeDocument] = []
        for p_doc in pje_catalog:
            name_c = p_doc.doc_name.lower().strip()
            type_c = p_doc.doc_type.lower().strip()
            if any(ex in name_c for ex in ["cota", "requerimento", "recebimento", "aditamento", "certidão"]):
                continue
            if name_c.startswith("denún") or name_c.startswith("denun") or type_c.startswith("denún") or type_c.startswith("denun") or "queixa" in name_c:
                matching_denuncias.append(p_doc)

        if not matching_denuncias:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if ("denún" in comb or "denun" in comb or "queixa" in comb) and "cota" not in comb:
                    matching_denuncias.append(p_doc)
                    break

        if not matching_denuncias:
            for p_doc in pje_catalog:
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if "petição inicial" in comb:
                    matching_denuncias.append(p_doc)
                    break

        denuncia_docs: List[PJeDocument] = []
        if matching_denuncias:
            latest = matching_denuncias[-1]
            denuncia_docs = [latest]
            for prev in reversed(matching_denuncias[:-1]):
                if prev.end_page + 1 == denuncia_docs[0].start_page or prev.doc_name == latest.doc_name:
                    denuncia_docs.insert(0, prev)
                else:
                    break
            denuncia_doc = denuncia_docs[0]
        else:
            denuncia_doc = None

        # Engine 5: Identify all defense documents
        defense_docs = self.defense_engine.find_all_defense_documents(pje_catalog, doc, reus_capa, advs_capa)
        resposta_doc = defense_docs[0].get("doc") if defense_docs else None

        if not resposta_doc:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if ("resposta" in comb and "acusação" in comb) or "defesa prévia" in comb:
                    resposta_doc = p_doc
                    break

        mandados_docs: List[PJeDocument] = []
        for p_doc in pje_catalog:
            comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
            if any(k in comb for k in ["mandado", "intimação", "certidão", "ofício", "diligência", "ato negativo", "ato positivo", "comprovante"]):
                mandados_docs.append(p_doc)

        # Engine 2: Locate Hearing Designation Act
        decisao_audiencia_doc, hearing_text = self.hearing_engine.find_hearing_document(pje_catalog, doc)

        # Extract raw texts of Denúncia and Resposta
        denuncia_text = (
            "\n\n".join(extract_doc_text(doc, d) for d in denuncia_docs)
            if denuncia_docs
            else (extract_doc_text(doc, denuncia_doc) if denuncia_doc else "")
        )
        resposta_text = extract_doc_text(doc, resposta_doc) if resposta_doc else ""

        # 3. Engine 3: Determine Act Type
        hearing_doc_name = decisao_audiencia_doc.doc_name if decisao_audiencia_doc else ""
        act_type = self.classification_engine.determine_act_type(
            filename=pdf_p.name,
            hearing_text=hearing_text,
            hearing_doc_name=hearing_doc_name,
            doc=doc,
            denuncia_doc=denuncia_doc,
            pje_catalog=pje_catalog,
        )

        # 4. Engine 2: Hearing Date, Time & Meeting Link
        hearing_datetime, hearing_link, is_in_person = self.hearing_engine.extract_hearing_details(
            hearing_text, pdf_p.name, doc, pje_catalog
        )

        # 5. Engine 4: Prosecutor Extraction
        prosecutor = self.prosecutor_engine.extract_prosecutor(denuncia_text, prom_capa, doc)

        # 6. Engine 6: Defendants & Qualification
        defendants, qualification_text = self.defendant_engine.extract_defendants_and_qual(
            denuncia_text, reus_capa, doc, pje_catalog, mandados_docs
        )

        # 7. Engine 7: Imputation & Crime Taxonomy
        imputation_text = self.imputation_engine.extract_imputation(denuncia_text)

        # 8. Engine 8: Summary of Facts & Special Notes
        facts_summary, special_notes = self.facts_engine.extract_facts(
            denuncia_text, act_type, pje_catalog, doc
        )

        # 9. Engine 9: Chronological Procedural History with IDs
        chronological_history = self.history_engine.build_chronological_history(
            pje_catalog, doc, reus_capa, advs_capa, defense_docs
        )

        # 10. Engine 10: Witnesses (Prosecution & Defense) with Unified Deduplication
        pros_witnesses, def_witnesses, def_note = self.witness_engine.extract_witnesses(
            denuncia_text, resposta_text, vitimas_capa, testemunhas_capa, mandados_docs, doc, defense_docs, reus_capa
        )

        # 11. Engine 5: Defense Counsel Representation
        defense_counsel = self.defense_engine.extract_defense_counsel(
            resposta_text, advs_capa, doc, defense_docs, reus_capa
        )

        # 12. Engine 11: Cross-Verification, Guardrails & Consensus Reconciliation
        final_summary, audit_report = self.corroboration_engine.reconcile_and_corroborate(
            case_number=case_number,
            act_type=act_type,
            hearing_datetime=hearing_datetime,
            hearing_link=hearing_link,
            is_in_person=is_in_person,
            prosecutor=prosecutor,
            defendants=defendants,
            defense_counsel=defense_counsel,
            qualification_text=qualification_text,
            imputation_text=imputation_text,
            facts_summary=facts_summary,
            chronological_history=chronological_history,
            prosecution_witnesses=pros_witnesses,
            defense_witnesses=def_witnesses,
            defense_witness_note=def_note,
            special_notes=special_notes,
            denuncia_text=denuncia_text,
            reus_capa=reus_capa,
            advs_capa=advs_capa,
            pje_catalog=pje_catalog,
            defense_docs=defense_docs,
        )

        self.last_audit_report = audit_report
        doc.close()
        return final_summary

    # =========================================================================
    # BACKWARD-COMPATIBLE METHOD DELEGATES (PRESERVING TEST AND CALLER API)
    # =========================================================================

    def _extract_case_number(self, doc: pymupdf.Document, filename: str) -> str:
        return self.capa_engine.extract_case_number(doc, filename)

    def _parse_capa_parties(
        self, doc: pymupdf.Document
    ) -> Tuple[List[str], List[str], List[str], List[str], Optional[str]]:
        return self.capa_engine.parse_capa_parties(doc)

    def _extract_doc_text(self, doc: pymupdf.Document, p_doc: Optional[PJeDocument]) -> str:
        return extract_doc_text(doc, p_doc)

    def _determine_act_type(
        self,
        filename: str,
        hearing_text: str,
        hearing_doc_name: str,
        doc: pymupdf.Document,
        denuncia_doc: Optional[PJeDocument],
        pje_catalog: List[PJeDocument],
        pscp_rev_doc: Optional[PJeDocument] = None,
        anpp_rev_doc: Optional[PJeDocument] = None,
    ) -> str:
        return self.classification_engine.determine_act_type(
            filename=filename,
            hearing_text=hearing_text,
            hearing_doc_name=hearing_doc_name,
            doc=doc,
            denuncia_doc=denuncia_doc,
            pje_catalog=pje_catalog,
            pscp_rev_doc=pscp_rev_doc,
            anpp_rev_doc=anpp_rev_doc,
        )

    def _extract_hearing_details(
        self,
        hearing_text: str,
        filename: str,
        doc: pymupdf.Document,
        pje_catalog: List[PJeDocument],
    ) -> Tuple[str, Optional[str], bool]:
        return self.hearing_engine.extract_hearing_details(hearing_text, filename, doc, pje_catalog)

    def _parse_datetime_from_text(self, txt: str) -> Optional[str]:
        return self.hearing_engine.parse_datetime_from_text(txt)

    def _extract_prosecutor(
        self, denuncia_text: str, prom_capa: Optional[str], doc: pymupdf.Document
    ) -> str:
        return self.prosecutor_engine.extract_prosecutor(denuncia_text, prom_capa, doc)

    def _extract_defendants_and_qual(
        self,
        denuncia_text: str,
        reus_capa: List[str],
        doc: pymupdf.Document,
        pje_catalog: List[PJeDocument],
        mandados_docs: List[PJeDocument],
    ) -> Tuple[List[Defendant], str]:
        return self.defendant_engine.extract_defendants_and_qual(
            denuncia_text, reus_capa, doc, pje_catalog, mandados_docs
        )

    def _extract_single_defendant_qualification(
        self, name: str, raw_qual: str, denuncia_text: str, ip_text: str
    ) -> str:
        return self.defendant_engine.extract_single_defendant_qualification(
            name, raw_qual, denuncia_text, ip_text
        )

    def _extract_imputation(self, denuncia_text: str) -> str:
        return self.imputation_engine.extract_imputation(denuncia_text)

    def _build_anpp_facts(
        self,
        doc: pymupdf.Document,
        pje_catalog: List[PJeDocument],
        denuncia_text: str,
    ) -> Tuple[str, Optional[str]]:
        return self.facts_engine.build_anpp_facts(doc, pje_catalog, denuncia_text)

    def _extract_facts(
        self,
        denuncia_text: str,
        act_type: str,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
    ) -> Tuple[str, Optional[str]]:
        return self.facts_engine.extract_facts(denuncia_text, act_type, pje_catalog, doc)

    def _extract_clean_narrative(self, raw_text: str) -> List[str]:
        return self.facts_engine.extract_clean_narrative(raw_text)

    def _find_all_defense_documents(
        self,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
        reus_capa: List[str],
        advs_capa: List[str],
    ) -> List[Dict]:
        return self.defense_engine.find_all_defense_documents(pje_catalog, doc, reus_capa, advs_capa)

    def _parse_defense_document(
        self,
        p_doc: PJeDocument,
        text: str,
        reus_capa: List[str],
        advs_capa: List[str],
        is_named_defense: bool = False,
    ) -> Optional[Dict]:
        return self.defense_engine.parse_defense_document(
            p_doc, text, reus_capa, advs_capa, is_named_defense
        )

    def _extract_defense_witness_names_from_text(self, text: str) -> List[str]:
        return self.witness_engine.extract_defense_witness_names_from_text(text)

    def _build_chronological_history(
        self,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
        reus_capa: Optional[List[str]] = None,
        advs_capa: Optional[List[str]] = None,
    ) -> List[HistoryItem]:
        return self.history_engine.build_chronological_history(
            pje_catalog, doc, reus_capa, advs_capa
        )

    def _summarize_history_act(self, p_doc: PJeDocument, doc: pymupdf.Document) -> str:
        return self.history_engine.summarize_history_act(p_doc, doc)

    def _extract_witnesses(
        self,
        denuncia_text: str,
        resposta_text: str,
        vitimas_capa: List[str],
        testemunhas_capa: List[str],
        mandados_docs: List[PJeDocument],
        doc: pymupdf.Document,
        defense_docs: Optional[List[Dict]] = None,
        reus_capa: Optional[List[str]] = None,
    ) -> Tuple[List[Witness], List[Witness], Optional[str]]:
        return self.witness_engine.extract_witnesses(
            denuncia_text, resposta_text, vitimas_capa, testemunhas_capa, mandados_docs, doc, defense_docs, reus_capa
        )

    def _extract_defense_counsel(
        self,
        resposta_text: str,
        advs_capa: List[str],
        doc: pymupdf.Document,
        defense_docs: Optional[List[Dict]] = None,
        reus_capa: Optional[List[str]] = None,
    ) -> str:
        return self.defense_engine.extract_defense_counsel(
            resposta_text, advs_capa, doc, defense_docs, reus_capa
        )
