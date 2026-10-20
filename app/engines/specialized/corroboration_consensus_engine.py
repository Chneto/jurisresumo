# -*- coding: utf-8 -*-
"""Specialized Engine 11: Cross-Verification, Guardrails & Consensus Engine (CorroborationConsensusEngine).

Responsible for:
1. Cross-verification and mutual corroboration between all specialized engines:
   - Capa vs Denúncia vs Defense Petitions vs Subpoenas.
   - Act Type vs Chronological History vs Procedural Hierarchy.
   - Penal Imputation vs Factual Narrative vs Statutory Taxonomy.
   - Witnesses vs Subpoenas vs Unified Defense Adoptions.
   - Defense Representation vs Represented Defendants Mapping.
2. Resolving conflicts and applying judicial consensus guardrails.
3. Enforcing procedural rules (e.g. strict trial section suppression in ANPP).
4. Generating a verifiable consensus audit trail.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.core.jev_decision_engine import JEVDecisionEngine
from app.core.models import (
    Defendant,
    HearingSummaryData,
    HistoryItem,
    PJeDocument,
    Witness,
)
from app.engines.specialized.common import (
    STATE_ORGANS_BLACKLIST_REGEX,
    _normalize_witness_name,
)


class ConsensusAuditReport(BaseModel):
    """Detailed audit report of cross-verifications and consensus adjustments performed."""
    case_number_verified: bool = True
    act_type_corroborated: bool = True
    hearing_datetime_verified: bool = True
    defendants_reconciled: int = 0
    witnesses_cross_checked: int = 0
    imputation_audited: bool = True
    defense_counsel_reconciled: bool = True
    confidence_score: float = 1.0
    adjustments_applied: List[str] = Field(default_factory=list)


class CorroborationConsensusEngine:
    """Specialized engine for cross-verifying outputs from all engines and establishing consensus."""

    def reconcile_and_corroborate(
        self,
        case_number: str,
        act_type: str,
        hearing_datetime: str,
        hearing_link: Optional[str],
        is_in_person: bool,
        prosecutor: str,
        defendants: List[Defendant],
        defense_counsel: str,
        qualification_text: str,
        imputation_text: str,
        facts_summary: str,
        chronological_history: List[HistoryItem],
        prosecution_witnesses: List[Witness],
        defense_witnesses: List[Witness],
        defense_witness_note: Optional[str],
        special_notes: Optional[str],
        denuncia_text: str,
        reus_capa: List[str],
        advs_capa: List[str],
        pje_catalog: List[PJeDocument],
        defense_docs: List[Dict],
    ) -> Tuple[HearingSummaryData, ConsensusAuditReport]:
        """Runs the complete multi-engine cross-verification suite and produces verified summary data."""
        report = ConsensusAuditReport()

        # 1. Corroborate Act Type against Chronological History & synchronize narrative/notes
        act_type, special_notes, facts_summary = self._corroborate_act_type(
            act_type=act_type,
            chronological_history=chronological_history,
            special_notes=special_notes,
            denuncia_text=denuncia_text,
            facts_summary=facts_summary,
            report=report,
        )

        # 2. Corroborate Hearing Datetime against Chronological History
        hearing_datetime = self._corroborate_hearing_datetime(
            hearing_datetime=hearing_datetime,
            chronological_history=chronological_history,
            report=report,
        )

        # 3. Corroborate Defendants and Qualifications (reconciling with Capa)
        defendants, qualification_text = self._corroborate_defendants(
            defendants=defendants,
            qualification_text=qualification_text,
            reus_capa=reus_capa,
            chronological_history=chronological_history,
            act_type=act_type,
            report=report,
        )

        # 4. Corroborate Imputation & Crime Taxonomy via JEV (stripping procedural articles)
        qualification_text, imputation_text = self._corroborate_imputation(
            qualification_text=qualification_text,
            imputation_text=imputation_text,
            denuncia_text=denuncia_text,
            report=report,
        )

        # 5. Corroborate Witnesses, Defense Notes and Anti-Defendant Collisions
        prosecution_witnesses, defense_witnesses, defense_witness_note = self._corroborate_witnesses(
            prosecution_witnesses=prosecution_witnesses,
            defense_witnesses=defense_witnesses,
            defense_witness_note=defense_witness_note,
            defense_docs=defense_docs,
            defendants=defendants,
            report=report,
        )

        # 6. Corroborate Defense Counsel mapping
        defense_counsel = self._corroborate_defense_counsel(
            defense_counsel=defense_counsel,
            defendants=defendants,
            defense_docs=defense_docs,
            advs_capa=advs_capa,
            report=report,
        )

        # 7. Apply ANPP Structural Rules (Zero Trial Sections)
        if act_type == "ANPP":
            qualification_text = ""
            imputation_text = ""
            chronological_history = []
            prosecution_witnesses = []
            defense_witnesses = []
            defense_witness_note = None
            report.adjustments_applied.append(
                "ANPP rule applied: suppressed qualification, imputation, chronological history, and witnesses."
            )

        summary_data = HearingSummaryData(
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
            prosecution_witnesses=prosecution_witnesses,
            defense_witnesses=defense_witnesses,
            defense_witness_note=defense_witness_note,
            special_notes=special_notes,
            closure_text="Cordial e respeitosamente,",
        )

        return summary_data, report

    def _corroborate_act_type(
        self,
        act_type: str,
        chronological_history: List[HistoryItem],
        special_notes: Optional[str],
        denuncia_text: str,
        facts_summary: str,
        report: ConsensusAuditReport,
    ) -> Tuple[str, Optional[str], str]:
        """Cross-checks act type with procedural history events and synchronizes facts/notes."""
        anpp_rev_items = [
            h for h in chronological_history
            if re.search(r"revog[^\n]*(?:anpp|acordo(?:\s+de\s+n[aã]o\s+persecu[cç][aã]o)?)\b", (h.description or ""), re.I)
        ]
        pscp_rev_items = [
            h for h in chronological_history
            if re.search(r"revog[^\n]*(?:pscp|suspens[aã]o(?:\s+condicional)?|sursis|benef[íi]cio\s+do\s+art\.?\s*89)\b", (h.description or ""), re.I)
        ]
        has_benefit_revocation = bool(anpp_rev_items or pscp_rev_items)
        has_suspensao_366 = any("366" in (h.description or "").lower() for h in chronological_history)

        # If act is ANPP or Sursis but there is an explicit revocation of benefit, it must be AIJ
        if act_type in ("ANPP", "SURSIS") and has_benefit_revocation:
            act_type = "AIJ"
            report.adjustments_applied.append(
                "Act type corrected from ANPP/SURSIS to AIJ due to revocation of benefit found in procedural history."
            )
            rev_notes = []
            if anpp_rev_items and pscp_rev_items:
                rev_notes.append(
                    f"Obs.: Audiência de Instrução e Julgamento designada após decisões que revogaram o Acordo de Não Persecução Penal (ANPP) (ID {anpp_rev_items[0].doc_id}) e a Suspensão Condicional do Processo (PSCP - art. 89 da Lei 9.099/95) (ID {pscp_rev_items[0].doc_id}), com a retomada do curso regular da ação penal."
                )
            elif anpp_rev_items:
                rev_notes.append(
                    f"Obs.: Audiência de Instrução e Julgamento designada após decisão que revogou o Acordo de Não Persecução Penal (ANPP) (ID {anpp_rev_items[0].doc_id}), com a retomada do curso regular da ação penal."
                )
            elif pscp_rev_items:
                rev_notes.append(
                    f"Obs.: Audiência de Instrução e Julgamento designada após decisão que revogou a Suspensão Condicional do Processo (PSCP - art. 89 da Lei 9.099/95) (ID {pscp_rev_items[0].doc_id}), com a retomada do curso regular da ação penal."
                )
            special_notes = " ".join(rev_notes) if rev_notes else special_notes

            # Restore AIJ factual narrative from denúncia if facts_summary was an ANPP synthesis
            if denuncia_text and ("Trata-se de ANPP" in facts_summary or "homologação de acordo" in facts_summary.lower() or not facts_summary):
                from app.engines.specialized.facts_narrative_engine import FactsNarrativeEngine
                narrative_paras = FactsNarrativeEngine().extract_clean_narrative(denuncia_text)
                if narrative_paras:
                    facts_summary = "\n\n".join(narrative_paras[:6])
                    report.adjustments_applied.append("Restored AIJ factual narrative from denúncia following ANPP revocation.")

        # If act is AIJ or standard but Art. 366 suspension exists without subsequent resumption, corroborate PAnP
        if act_type == "AIJ" and has_suspensao_366 and not has_benefit_revocation:
            for h in reversed(chronological_history):
                if "produção antecipada" in (h.description or "").lower() or "art. 366" in (h.description or "").lower():
                    act_type = "PAnP"
                    report.adjustments_applied.append(
                        "Act type corroborated as PAnP due to Art. 366 CPP suspension in procedural history."
                    )
                    break

        return act_type, special_notes, facts_summary

    def _corroborate_hearing_datetime(
        self,
        hearing_datetime: str,
        chronological_history: List[HistoryItem],
        report: ConsensusAuditReport,
    ) -> str:
        """Cross-checks hearing datetime against chronological history events if missing or uncertain."""
        if not hearing_datetime or hearing_datetime.strip().lower() in ("data a definir", "a definir", ""):
            from app.engines.specialized.hearing_details_engine import HearingDetailsEngine
            h_engine = HearingDetailsEngine()
            for h in reversed(chronological_history):
                desc = h.description or ""
                if any(k in desc.lower() for k in ["audiência", "audiencia", "pauta"]):
                    dt_cand = h_engine.parse_datetime_from_text(desc)
                    if dt_cand:
                        report.adjustments_applied.append(f"Recovered hearing datetime '{dt_cand}' from chronological history ID {h.doc_id}.")
                        return dt_cand
        return hearing_datetime

    def _corroborate_defendants(
        self,
        defendants: List[Defendant],
        qualification_text: str,
        reus_capa: List[str],
        chronological_history: List[HistoryItem],
        act_type: str,
        report: ConsensusAuditReport,
    ) -> Tuple[List[Defendant], str]:
        """Cross-checks defendant list against Capa, state organ filters, and Art. 366 suspension status."""
        valid_defendants: List[Defendant] = []
        seen_names = set()

        # 1. Clean existing extracted defendants
        for d in defendants:
            if STATE_ORGANS_BLACKLIST_REGEX.search(d.name.strip()):
                report.adjustments_applied.append(f"Pruned state organ '{d.name}' from defendants list.")
                continue
            norm = d.name.strip().lower()
            if norm not in seen_names:
                seen_names.add(norm)
                if act_type == "PAnP":
                    d.status = (
                        "O réu, citado por edital, não atendeu ao chamamento judicial, encontrando-se o processo "
                        "e o prazo prescricional suspensos com relação a ele."
                    )
                valid_defendants.append(d)

        # 2. Cross-corroborate against Capa: restore any missing legitimate defendant
        reus_capa_clean = [
            r.strip() for r in (reus_capa or [])
            if r.strip() and not STATE_ORGANS_BLACKLIST_REGEX.search(r.strip())
        ]
        for r_name in reus_capa_clean:
            norm_c = r_name.lower()
            if not any(norm_c == s or (len(norm_c) > 4 and norm_c in s) or (len(s) > 4 and s in norm_c) for s in seen_names):
                seen_names.add(norm_c)
                status_default = "respondendo ao processo em liberdade"
                if act_type == "PAnP":
                    status_default = (
                        "O réu, citado por edital, não atendeu ao chamamento judicial, encontrando-se o processo "
                        "e o prazo prescricional suspensos com relação a ele."
                    )
                valid_defendants.append(
                    Defendant(
                        name=r_name.title(),
                        status=status_default,
                        qualification=f"{r_name.upper()}, qualificação nos autos.",
                    )
                )
                report.adjustments_applied.append(f"Restored defendant '{r_name}' from Capa missing in body extraction.")

        # 3. Ensure qualification_text contains entries for all valid defendants
        if valid_defendants:
            qual_paras = [q.strip() for q in qualification_text.split("\n\n") if q.strip()]
            for d in valid_defendants:
                d_first = d.name.split()[0].lower() if d.name.split() else ""
                d_last = d.name.split()[-1].lower() if len(d.name.split()) > 1 else ""
                has_qual = any(
                    d.name.lower() in q.lower() or (len(d_first) > 3 and len(d_last) > 3 and d_first in q.lower() and d_last in q.lower())
                    for q in qual_paras
                )
                if not has_qual:
                    qual_paras.append(f"{d.name.upper()}, qualificação nos autos.")
                    report.adjustments_applied.append(f"Appended default qualification entry for defendant '{d.name}'.")
            qualification_text = "\n\n".join(qual_paras)

        report.defendants_reconciled = len(valid_defendants)
        return valid_defendants, qualification_text

    def _corroborate_imputation(
        self,
        qualification_text: str,
        imputation_text: str,
        denuncia_text: str,
        report: ConsensusAuditReport,
    ) -> Tuple[str, str]:
        """Audits and complements qualification and imputation via JEV Decision Engine, purging procedural/CF articles."""
        procedural_cf_patterns = [
            r"(?:,\s*|\s+c/c\s+|\s+comb\s+|\s+combinado\s+com\s+|\s+e\s+)?\bart(?:igo)?s?\b\.?\s*(?:396(?:-A)?|399|41|383|384)\b(?:[^\n;)]*?)(?:do\s+CPP|do\s+C[oó]digo\s+de\s+Processo\s+Penal)\b",
            r"(?:,\s*|\s+c/c\s+|\s+comb\s+|\s+combinado\s+com\s+|\s+e\s+)?\bart(?:igo)?s?\b\.?\s*(?:129|5[º°]?|5)\b(?:[^\n;)]*?)(?:da\s+CF(?:/88)?|da\s+Constitui[cç][aã]o(?:\s+Federal)?)\b",
            r"\bdo\s+CPP\b",
        ]
        cleaned_imp = imputation_text
        for pat in procedural_cf_patterns:
            if re.search(pat, cleaned_imp, re.I):
                cleaned_imp = re.sub(pat, "", cleaned_imp, flags=re.I).strip(" ,.;c/")
                report.adjustments_applied.append("Purged non-penal procedural CPP / CF article from imputation.")

        cleaned_imp = re.sub(r"\s+", " ", cleaned_imp).strip(" ,.;c/")

        audited_qual, audited_imp = JEVDecisionEngine.get_instance().audit_qualification_and_imputation(
            qualification_text, cleaned_imp or imputation_text, denuncia_text
        )

        if audited_imp != imputation_text:
            report.adjustments_applied.append("Imputation complemented with missing statutory references via JEV.")
        if audited_qual != qualification_text:
            report.adjustments_applied.append("Qualification adjusted via JEV audit.")

        return audited_qual, audited_imp

    def _corroborate_witnesses(
        self,
        prosecution_witnesses: List[Witness],
        defense_witnesses: List[Witness],
        defense_witness_note: Optional[str],
        defense_docs: List[Dict],
        defendants: List[Defendant],
        report: ConsensusAuditReport,
    ) -> Tuple[List[Witness], List[Witness], Optional[str]]:
        """Ensures unified witness numbering, role clarity, anti-defendant collision, and proper defense notes."""
        def_names = {_normalize_witness_name(d.name).strip().lower() for d in defendants}

        # Anti-defendant collision check
        cleaned_pros: List[Witness] = []
        for w in prosecution_witnesses:
            w_norm = _normalize_witness_name(w.name).strip().lower()
            if w_norm in def_names or any(w_norm == dn for dn in def_names):
                report.adjustments_applied.append(f"Pruned defendant collision from prosecution witness list: '{w.name}'.")
                continue
            cleaned_pros.append(w)

        cleaned_def: List[Witness] = []
        for w in defense_witnesses:
            w_norm = _normalize_witness_name(w.name).strip().lower()
            if w_norm in def_names or any(w_norm == dn for dn in def_names):
                report.adjustments_applied.append(f"Pruned defendant collision from defense witness list: '{w.name}'.")
                continue
            cleaned_def.append(w)

        # Consecutive numbering
        for i, w in enumerate(cleaned_pros, start=1):
            w.number = i
        for i, w in enumerate(cleaned_def, start=1):
            w.number = i

        report.witnesses_cross_checked = len(cleaned_pros) + len(cleaned_def)

        # Defense note reconciliation
        if cleaned_def:
            defense_witness_note = None
        elif not defense_witness_note:
            has_adoptions = any(d.get("adopts_mp_witnesses", False) for d in defense_docs)
            if has_adoptions:
                defense_witness_note = "A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia."
            else:
                defense_witness_note = "Não há testemunhas de defesa arroladas."

        return cleaned_pros, cleaned_def, defense_witness_note

    def _corroborate_defense_counsel(
        self,
        defense_counsel: str,
        defendants: List[Defendant],
        defense_docs: List[Dict],
        advs_capa: List[str],
        report: ConsensusAuditReport,
    ) -> str:
        """Cross-checks defense counsel representation for all defendants."""
        if not defense_counsel or defense_counsel.strip() == "":
            if any("defensor" in a.lower() for a in advs_capa):
                defense_counsel = "Assistido pela Defensoria Pública"
            else:
                defense_counsel = "Assistido pela Defensoria Pública"
            report.adjustments_applied.append("Defaulted unassigned defense counsel to Defensoria Pública.")
            return defense_counsel

        # If multiple defendants, verify that all defendants are accounted for
        if len(defendants) > 1:
            unassigned_defs = []
            for d in defendants:
                d_first = d.name.split()[0].lower() if d.name.split() else ""
                d_last = d.name.split()[-1].lower() if len(d.name.split()) > 1 else ""
                is_mentioned = (
                    d.name.lower() in defense_counsel.lower()
                    or (len(d_first) > 3 and len(d_last) > 3 and d_first in defense_counsel.lower() and d_last in defense_counsel.lower())
                )
                if not is_mentioned:
                    unassigned_defs.append(d.name.title())

            if unassigned_defs:
                names_str = ", ".join(unassigned_defs)
                if "defensoria" in defense_counsel.lower():
                    # If defensoria is already mentioned without specific names, it already covers them
                    if not re.search(r"em\s+defesa\s+de", defense_counsel, re.I):
                        pass
                    else:
                        defense_counsel += f"; Assistido(s) pela Defensoria Pública (em defesa de {names_str})"
                        report.adjustments_applied.append(f"Appended Defensoria Pública coverage for unassigned defendant(s): {names_str}.")
                else:
                    defense_counsel += f"; Assistido(s) pela Defensoria Pública (em defesa de {names_str})"
                    report.adjustments_applied.append(f"Appended Defensoria Pública coverage for unassigned defendant(s): {names_str}.")

        return defense_counsel

