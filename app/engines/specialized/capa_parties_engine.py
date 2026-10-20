# -*- coding: utf-8 -*-
"""Specialized Engine 1: Capa & Parties Ingestion Engine (CapaPartiesEngine).

Responsible for:
1. Extracting the canonical 20-digit CNJ case number from filename or first pages.
2. Parsing Page 1 Capa Parties (Polo Ativo, Polo Passivo, Vítimas, Testemunhas, Promotor).
3. Filtering state organs mistakenly listed in the passive pole (anti-delegacia/estado/defensoria).
4. Handling registered social vs civil names.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import List, Optional, Tuple
import pymupdf

from app.engines.specialized.common import (
    CNJ_REGEX,
    STATE_ORGANS_BLACKLIST_REGEX,
)


class CapaPartiesEngine:
    """Specialized engine for Capa analysis, case numbering, and procedural pole extraction."""

    def extract_case_number(self, doc: pymupdf.Document, filename: str) -> str:
        """Finds the standard 20-digit CNJ process number."""
        match_fn = CNJ_REGEX.search(filename)
        if match_fn:
            return match_fn.group(1)

        for i in range(min(len(doc), 5)):
            txt = doc[i].get_text()
            match_doc = CNJ_REGEX.search(txt)
            if match_doc:
                return match_doc.group(1)

        return "0000000-00.0000.8.20.0000"

    def parse_capa_parties(
        self, doc: pymupdf.Document
    ) -> Tuple[List[str], List[str], List[str], List[str], Optional[str]]:
        """Extracts parties and roles from Page 1 Capa with multi-line buffering and state organ exclusion."""
        reus: List[str] = []
        advs: List[str] = []
        vitimas: List[str] = []
        testemunhas: List[str] = []
        prom: Optional[str] = None

        if len(doc) == 0:
            return reus, advs, vitimas, testemunhas, prom

        page1_lines = doc[0].get_text().split("\n")
        in_parties = False
        pending_lines: List[str] = []

        def process_entry(combined: str):
            nonlocal prom
            c = combined.strip()
            if not c:
                return
            c_upper = c.upper()

            # Find role tag
            m_role = re.search(
                r"\((AUTOR(?:A)?|R[EÉ]U|INVESTIGAD[OA]|INDICIAD[OA]|ACUSAD[OA]|QUERELAD[OA]|QUERELANTE|AUTOR(?:A)?\s+DO\s+FATO|ADVOGAD[OA]|DEFENSOR(?:IA)?(?:\s*\([^)]*\))?|V[IÍ]TIMA|TESTEMUNHA|TERCEIRO\s+INTERESSADO|CUSTOS\s+LEGIS)\)",
                c,
                re.I,
            )
            role_type = m_role.group(1).upper() if m_role else ""

            # Extract name
            if "registrado" in c.lower() and "civilmente como" in c.lower():
                m_civ = re.split(r"registrado(?:\(a\))?\s+civilmente\s+como\s+", c, flags=re.I)
                raw_name = m_civ[0].strip()
                if not raw_name and len(m_civ) > 1:
                    raw_name = re.sub(r"\(.*?\)", "", m_civ[1]).strip()
            else:
                raw_name = re.sub(r"\([^)]*\([^)]*\)[^)]*\)|\([^)]*\)", "", c).strip()

            raw_name = re.sub(r"^[A-Z]+:\s*", "", raw_name).strip()
            raw_name = re.sub(r"\s+", " ", raw_name).strip().rstrip(" )")

            if any(r in role_type or r in c_upper for r in ["(REU)", "(RÉU)", "(INVESTIGADO)", "(INVESTIGADA)", "(INDICIADO)", "(INDICIADA)", "(ACUSADO)", "(ACUSADA)", "(QUERELADO)", "(QUERELADA)", "(AUTOR DO FATO)", "(AUTORA DO FATO)"]):
                if raw_name and len(raw_name) > 3 and not STATE_ORGANS_BLACKLIST_REGEX.search(raw_name) and raw_name not in reus:
                    reus.append(raw_name)
            elif "(ADVOGADO)" in c_upper or "(DEFENSOR" in c_upper or "DEFENSORIA" in role_type:
                if raw_name and len(raw_name) > 3 and raw_name not in advs:
                    advs.append(raw_name)
            elif "(VÍTIMA)" in c_upper or "(VITIMA)" in c_upper:
                if raw_name and len(raw_name) > 3 and raw_name not in vitimas:
                    vitimas.append(raw_name)
            elif "(TESTEMUNHA)" in c_upper:
                if raw_name and len(raw_name) > 3 and raw_name not in testemunhas:
                    testemunhas.append(raw_name)
            elif "(AUTOR)" in c_upper and ("PROMOTORIA" in c_upper or "MINISTÉRIO" in c_upper):
                prom_m = re.search(r"(\d+ª?\s+Promotoria[^\n)]+)", c, re.I)
                if prom_m:
                    prom = f"Dr. Promotor de Justiça ({prom_m.group(1).strip()})"
                else:
                    prom = "Dr. Promotor de Justiça"

        for line in page1_lines:
            l = line.strip()
            if not l:
                continue
            l_upper = l.upper()

            if "PARTES" in l_upper:
                in_parties = True
                continue
            if in_parties and any(k in l_upper for k in ["DOCUMENTOS", "ID.", "DATA\tDOCUMENTO", "TABELA DE DOCUMENTOS"]):
                if pending_lines:
                    process_entry(" ".join(pending_lines))
                    pending_lines = []
                in_parties = False
                break
            if not in_parties:
                continue
            if "PROCURADOR/TERCEIRO VINCULADO" in l_upper:
                continue

            pending_lines.append(l)
            comb = " ".join(pending_lines)

            # Check if this closes a role parenthesis
            m_role = re.search(
                r"\((?:AUTOR(?:A)?|R[EÉ]U|INVESTIGAD[OA]|INDICIAD[OA]|ACUSAD[OA]|QUERELAD[OA]|QUERELANTE|AUTOR(?:A)?\s+DO\s+FATO|ADVOGAD[OA]|DEFENSOR(?:IA)?(?:\s*\([^)]*\))?|V[IÍ]TIMA|TESTEMUNHA|TERCEIRO\s+INTERESSADO|CUSTOS\s+LEGIS)\)",
                comb,
                re.I,
            )
            if m_role:
                process_entry(comb)
                pending_lines = []
            elif len(pending_lines) >= 3:
                process_entry(comb)
                pending_lines = []

        if pending_lines:
            process_entry(" ".join(pending_lines))

        # Fallback if no reus found via structured parsing
        if not reus:
            prev_line = ""
            for line in page1_lines:
                l = line.strip()
                l_upper = l.upper()
                if any(k in l_upper for k in ["(REU)", "(RÉU)", "(INVESTIGADO)", "(INVESTIGADA)", "(INDICIADO)", "(INDICIADA)", "(ACUSADO)", "(ACUSADA)", "(QUERELADO)", "(QUERELADA)", "(AUTOR DO FATO)", "(AUTORA DO FATO)"]):
                    name = re.sub(r"\((?:R[EÉ]U|INVESTIGAD[OA]|INDICIAD[OA]|ACUSAD[OA]|QUERELAD[OA]|AUTOR(?:A)?\s+DO\s+FATO)\)", "", l, flags=re.I).strip()
                    if not name and prev_line:
                        name = prev_line
                    name = re.sub(r"^[A-Z]+:\s*", "", name).strip()
                    if name and len(name) > 3 and not STATE_ORGANS_BLACKLIST_REGEX.search(name) and name not in reus:
                        reus.append(name.strip())
                prev_line = l

        # Supplement prom with promotoria number if found anywhere on Capa
        if prom and "promotoria" not in prom.lower():
            for l in page1_lines:
                prom_m = re.search(r"(\d+ª?\s+Promotoria[^\n)]+)", l, re.I)
                if prom_m:
                    prom = f"Dr. Promotor de Justiça ({prom_m.group(1).strip()})"
                    break

        return reus, advs, vitimas, testemunhas, prom
