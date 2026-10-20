# -*- coding: utf-8 -*-
"""Specialized Engine 4: Prosecutor Identification Engine (ProsecutorEngine).

Responsible for:
1. Extracting the prosecutor's personal name and promotoria assignment.
2. Parsing digital signatures in the accusatory complaint (Denúncia/Cota).
3. Filtering address contaminants (street names, notary names).
4. Fallback to Capa promotoria identification.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Optional
import pymupdf


class ProsecutorEngine:
    """Specialized engine for prosecuting attorney / MP identification."""

    def extract_prosecutor(
        self,
        denuncia_text: str,
        prom_capa: Optional[str],
        doc: pymupdf.Document,
    ) -> str:
        """Extracts the prosecutor's personal name and promotoria."""
        # 1. Search digital signature in Denúncia (most reliable for actual prosecutor)
        sig_matches = re.findall(
            r"Assinado\s+eletronicamente\s+por:\s*([A-ZÁÉÍÓÚÂÊÔÃÕ\s]+?)\s*-\s*\d{2}/\d{2}/\d{4}",
            denuncia_text,
        )
        for sig in sig_matches:
            name = sig.strip()
            if len(name) > 5 and not any(k in name.lower() for k in ["secretaria", "escriv", "diretor", "tribunal", "rua", "vara", "comarca"]):
                prom_name = f"Dr. {name.title()}"
                if prom_capa and "promotoria" in prom_capa.lower():
                    prom_num = re.search(r"((?:\d+ª?\s+)?Promotoria[^\n()]+)", prom_capa, re.I)
                    if prom_num:
                        prom_name += f" ({prom_num.group(1).strip()})"
                return prom_name

        # 2. Search header/title in Denúncia, strictly excluding street/avenue names
        match = re.search(
            r"(?<!Rua\s)(?<!Avenida\s)(?:Promotor(?:a)?(?:\s+de\s+Justi[çc]a)?[:\s\n]+(?:Dr\(?a\)?\.?\s+)?)([A-ZÁÉÍÓÚÂÊÔÃÕ][A-Za-záéíóúâêôãõ\s]+(?:\s+Filho|\s+Júnior|\s+Neto|\s+Sobrinho)?)",
            denuncia_text,
            re.IGNORECASE,
        )
        if match:
            name = match.group(1).strip().split("\n")[0].strip()
            if len(name) > 3 and not any(ex in name.lower() for ex in ["estado", "ministério", "promotoria", "justiça", "comarca", "manoel alves pessoa neto"]):
                prom_name = f"Dr. {name.title()}"
                if prom_capa and "promotoria" in prom_capa.lower():
                    prom_num = re.search(r"((?:\d+ª?\s+)?Promotoria[^\n()]+)", prom_capa, re.I)
                    if prom_num:
                        prom_name += f" ({prom_num.group(1).strip()})"
                return prom_name

        # 3. Fallback to prom_capa
        if prom_capa:
            clean_prom = re.sub(r"^[A-Z\s]+:\s*", "", prom_capa).strip()
            clean_prom = re.sub(r"\(AUTOR\)", "", clean_prom, flags=re.I).strip()
            clean_prom = re.sub(r"\(P[oó]lo[^\)]*\)", "", clean_prom, flags=re.I).strip()
            prom_num = re.search(r"((?:\d+ª?\s+)?Promotoria[^\n()]+)", clean_prom, re.I)
            if prom_num:
                return f"Dr. Promotor de Justiça ({prom_num.group(1).strip()})"
            return f"Dr. Promotor de Justiça ({clean_prom})"

        return "Dr. Promotor de Justiça"
