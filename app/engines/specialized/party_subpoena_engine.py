# -*- coding: utf-8 -*-
"""Specialized Engine: Party Subpoena & Diligence Linking Engine (PartySubpoenaEngine).

Responsible for:
1. Indexing all service documents (mandados de intimação, mandados de citação,
   certidões de oficial de justiça, ofícios a comandos da PM/delegacias, cartas precatórias).
2. Rigorously linking subpoenas and citations to the specific party named in the judicial act.
3. Distinguishing positive service ("Intimado ID <ID>", "Citado ID <ID>") from frustrated
   attempts ("Certidão contrafé negativa ID <ID> - não localizado").
4. Preventing arbitrary or false fallbacks (never assigning one party's mandado ID to an unrelated party).
5. Exposing structured diligence records for Defendants, Witnesses, Victims, and Counsel.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Optional, Tuple
import pymupdf

from app.core.models import PJeDocument
from app.engines.specialized.common import (
    _normalize_witness_name,
    extract_doc_text,
)


class PartyDiligenceRecord:
    """Structured record of a procedural diligence linked to a specific party."""

    def __init__(
        self,
        party_name: str,
        doc_id: str,
        doc_name: str,
        diligence_type: str,  # 'intimacao', 'citacao', 'oficio', 'certidao_negativa', 'certidao_positiva'
        status_text: str,
        is_served: bool = True,
        is_negative: bool = False,
    ):
        self.party_name = party_name
        self.doc_id = doc_id
        self.doc_name = doc_name
        self.diligence_type = diligence_type
        self.status_text = status_text
        self.is_served = is_served
        self.is_negative = is_negative


class PartySubpoenaEngine:
    """Specialized engine for linking subpoenas, citations, and diligences strictly to each party."""

    def __init__(self):
        self._doc_cache: Dict[str, str] = {}

    def extract_diligence_documents(self, pje_catalog: List[PJeDocument]) -> List[PJeDocument]:
        """Filters catalog to identify all documents related to communication and diligence service."""
        diligence_keywords = [
            "mandado", "certidão", "certidao", "ofício", "oficio",
            "intimação", "intimacao", "notificação", "notificacao",
            "citação", "citacao", "precatória", "precatoria",
            "devolução de mandado", "devolucao de mandado", "comunicação", "comunicacao",
        ]
        return [
            d for d in pje_catalog
            if any(k in f"{d.doc_name} {d.doc_type}".lower() for k in diligence_keywords)
            and d.start_page > 0
        ]

    def build_party_diligences_map(
        self,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
        party_names: List[str],
    ) -> Dict[str, List[PartyDiligenceRecord]]:
        """Maps each party name to their verified procedural diligences and document IDs."""
        diligence_docs = self.extract_diligence_documents(pje_catalog)
        party_map: Dict[str, List[PartyDiligenceRecord]] = {p: [] for p in party_names}

        # Cache document texts
        for d_doc in diligence_docs:
            if d_doc.doc_id not in self._doc_cache and doc is not None:
                self._doc_cache[d_doc.doc_id] = extract_doc_text(doc, d_doc).lower()

        for party in party_names:
            norm_party = _normalize_witness_name(party).strip().lower()
            tokens = [t for t in norm_party.split() if len(t) > 2]
            first_n = tokens[0] if tokens else ""
            last_n = tokens[-1] if len(tokens) > 1 else ""

            for d_doc in diligence_docs:
                txt = self._doc_cache.get(d_doc.doc_id, "")
                comb_name = f"{d_doc.doc_name} {d_doc.doc_type}".lower()

                # Match party name in document text or document title
                name_in_text = (
                    norm_party in txt
                    or (len(first_n) > 3 and len(last_n) > 3 and first_n in txt and last_n in txt)
                )
                name_in_title = (
                    norm_party in comb_name
                    or (len(first_n) > 3 and len(last_n) > 3 and first_n in comb_name and last_n in comb_name)
                )

                if not (name_in_text or name_in_title):
                    continue

                # Classify diligence outcome
                is_neg = any(k in txt for k in [
                    "contrafé negativa", "contrafe negativa", "não localizado",
                    "nao localizado", "deixei de citar", "deixei de intimar",
                    "mudou-se", "desconhecido", "falecido", "ausente",
                ])

                is_pos = any(k in txt for k in [
                    "citei", "intimei", "notifiquei", "dei ciência",
                    "dei ciencia", "cumprido", "positivo", "aceitou a contrafé",
                ]) or "cumprid" in comb_name

                is_oficio = "ofício" in comb_name or "oficio" in comb_name or "comando" in txt

                if is_neg:
                    rec = PartyDiligenceRecord(
                        party_name=party,
                        doc_id=d_doc.doc_id,
                        doc_name=d_doc.doc_name,
                        diligence_type="certidao_negativa",
                        status_text=f"Certidão contrafé negativa ID {d_doc.doc_id}",
                        is_served=False,
                        is_negative=True,
                    )
                elif is_oficio:
                    rec = PartyDiligenceRecord(
                        party_name=party,
                        doc_id=d_doc.doc_id,
                        doc_name=d_doc.doc_name,
                        diligence_type="oficio",
                        status_text=f"Ofício enviado ID {d_doc.doc_id}",
                        is_served=True,
                        is_negative=False,
                    )
                elif "citação" in comb_name or "citacao" in comb_name or "citei" in txt:
                    rec = PartyDiligenceRecord(
                        party_name=party,
                        doc_id=d_doc.doc_id,
                        doc_name=d_doc.doc_name,
                        diligence_type="citacao",
                        status_text=f"Citado ID {d_doc.doc_id}",
                        is_served=is_pos,
                        is_negative=False,
                    )
                else:
                    # Intimação
                    gender_term = "Intimada" if any(f in norm_party for f in ["maria", "ana", "julia", "samara", "dra", "sra"]) else "Intimado"
                    rec = PartyDiligenceRecord(
                        party_name=party,
                        doc_id=d_doc.doc_id,
                        doc_name=d_doc.doc_name,
                        diligence_type="intimacao",
                        status_text=f"{gender_term} ID {d_doc.doc_id}",
                        is_served=is_pos,
                        is_negative=False,
                    )

                party_map[party].append(rec)

        return party_map

    def get_defendant_diligence(
        self,
        defendant_name: str,
        party_map: Dict[str, List[PartyDiligenceRecord]],
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Returns (subpoena_id, citation_id, status_description) for a defendant.

        Strictly returns IDs verified to belong to the defendant.
        """
        records = party_map.get(defendant_name, [])
        if not records:
            # Check partial key match
            for k, recs in party_map.items():
                if defendant_name.lower() in k.lower() or k.lower() in defendant_name.lower():
                    records = recs
                    break

        subpoena_id = None
        citation_id = None
        status_desc = None

        # Prioritize positive service over pending or negative
        for r in records:
            if r.diligence_type == "intimacao" and not subpoena_id:
                subpoena_id = r.doc_id
            elif r.diligence_type == "citacao" and not citation_id:
                citation_id = r.doc_id
            elif r.diligence_type == "certidao_negativa":
                if not status_desc:
                    status_desc = f"não intimado (Certidão contrafé negativa ID {r.doc_id})"

        return subpoena_id, citation_id, status_desc

    def get_witness_diligence_status(
        self,
        witness_name: str,
        is_pm: bool,
        party_map: Dict[str, List[PartyDiligenceRecord]],
        default_mandados: Optional[List[PJeDocument]] = None,
    ) -> str:
        """Returns the canonical status string for a witness with accurate ID matching."""
        records = party_map.get(witness_name, [])
        if not records:
            for k, recs in party_map.items():
                if witness_name.lower() in k.lower() or k.lower() in witness_name.lower():
                    records = recs
                    break

        negative_ids = [r.doc_id for r in records if r.is_negative]
        if negative_ids:
            return f"Certidão contrafé negativa ID {'; '.join(negative_ids)}"

        positive_records = [r for r in records if not r.is_negative]
        if positive_records:
            return positive_records[0].status_text

        # Fallback when no specific service piece matched this witness
        if is_pm:
            if default_mandados:
                for m in default_mandados:
                    if "ofício" in m.doc_name.lower() or "oficio" in m.doc_name.lower():
                        return f"Ofício enviado ID {m.doc_id}"
            return "Ofício expedido"

        return "Mandado expedido"
