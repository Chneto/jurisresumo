# -*- coding: utf-8 -*-
"""Specialized Engine 7: Penal Imputation & Crime Taxonomy Engine (ImputationTaxonomyEngine).

Responsible for:
1. Extracting penal imputation articles, paragraphs (§), incisos, and alíneas from the complaint.
2. Capturing special criminal legislation (ECA, Lei de Drogas, Desarmamento, Maria da Penha, CTB).
3. Capturing crime concurrence (arts. 69, 70, 71 do Código Penal - material, formal, continuado).
4. Strict filtering of procedural (CPP) and constitutional (CF) articles to prevent false crimes.
5. Annotating the imputation with official legal nomenclature via Crime Taxonomy.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import List

from app.core.crime_taxonomy import annotate_imputation_text
from app.core.jev_decision_engine import is_procedural_or_constitutional
from app.engines.specialized.common import _clean_legal_text


class ImputationTaxonomyEngine:
    """Specialized engine for criminal charge extraction and statutory taxonomy annotation."""

    def extract_imputation(self, denuncia_text: str) -> str:
        """Extracts penal imputation articles and full crime title, preserving all articles, paragraphs, incisos, special laws and crime concurrence."""
        if not denuncia_text:
            return "Artigo de lei a ser apurado"

        base_imputation = ""

        # 1. Search for explicit section header (e.g. 'VI) Imputação legal' or 'DA IMPUTAÇÃO')
        m_sec = re.search(
            r"(?:(?:VI|V|IV|III|II|I)\)?\s*Imputa[cç][aã]o(?:\s*legal)?|DA\s+IMPUTA[CÇ][AÃ]O|Tipifica[cç][aã]o\s*legal|Tipifica[cç][aã]o)[:\s\n]+([A-ZÁÉÍÓÚ][^\n]+(?:\n(?!\b(?:VII|VI|V|IV|III|II|I\)|DOS\s+PEDIDOS|DO\s+PEDIDO|ROL|FATOS)\b)[^\n]+)?)",
            denuncia_text,
            re.IGNORECASE,
        )
        if m_sec:
            raw_imp = m_sec.group(1).strip()
            is_narrative = any(k in raw_imp.lower() for k in ["imputa à querelada", "imputa ao querelado", "consta dos autos", "o ministério público", "fatos criminosos autônomos"])
            has_penal_article = bool(re.search(r"\bart(?:igo)?s?\b\.?\s*\d+", raw_imp, re.I))
            if has_penal_article and not is_narrative and len(raw_imp) <= 250:
                raw_imp = _clean_legal_text(raw_imp)
                raw_imp = re.sub(r"\s+", " ", raw_imp).strip()
                base_imputation = raw_imp

        # 2. Search for standard closing / pedidos phrase in Denúncia or Queixa-Crime
        if not base_imputation:
            pat_crime = re.compile(
                r"(?:condena[cç][aã]o\s+(?:d[oa]\s+(?:querelad[oa]|acusad[oa]|denunciad[oa]|r[eé]u)[a-z]*|d[eo]s?\s+(?:acusad[oa]s?|denunciad[oa]s?|r[eé]us?))?\s*)?"
                r"(?:como\s+incurs[oa]\s+n[ao]s?\s+(?:penas|san[cç][oõ]es|disposi[cç][oõ]es)\s+d[ao]\s*|incurso\s+n[ao]s?\s+(?:penas|san[cç][oõ]es|disposi[cç][oõ]es)\s+d[ao]\s*|"
                r"condena[cç][aã]o\s+(?:d[oa]\s+querelad[oa]\s+)?pela\s+pr[aá]tica[,\s]+|"
                r"(?:em\s+raz[aã]o\s+d[oe]|pelo)\s+(?:cometimento\s+do\s+)?crime\s+previsto\s+n[ao]\s+)"
                r"([\s\S]*?(?:art(?:igo)?\.?\s*\d+[\s\S]*?))"
                r"(?=[;.]\s*(?:\n\s*[a-zA-ZÁÉÍÓÚ\d\-]|\n\s*\n|$)|$)",
                re.IGNORECASE,
            )
            m_crime = pat_crime.search(_clean_legal_text(denuncia_text))
            if m_crime:
                raw_imp = m_crime.group(1).strip()
                raw_imp = _clean_legal_text(raw_imp)
                raw_imp = re.sub(r"\s+", " ", raw_imp).strip()
                if len(raw_imp) > 5:
                    base_imputation = raw_imp

        # 3. Global scan for substantive penal articles, paragraphs, incisos, special laws and concurrence
        all_articles: List[str] = []

        # Penal articles with paragraphs (§), incisos, alíneas, e.g., "art. 157, § 2º, II, e § 2º-A, I, do CP"
        penal_rx = re.compile(
            r"\bart(?:igo)?s?\b\.?\s*\d+(?:-[A-Z])?\b"
            r"(?:\s*,\s*§\s*\d+[º°]?(?:-[A-Z])?|\s+§\s*\d+[º°]?(?:-[A-Z])?)*"
            r"(?:\s*,\s*(?:inciso\s+)?[I|V|X|L|C|D|M]+\b|\s+(?:inciso\s+)?[I|V|X|L|C|D|M]+\b)*"
            r"(?:\s*,\s*al[íi]nea\s+[a-z]|\s+al[íi]nea\s+[a-z])*"
            r"(?:\s+(?:c/c|comb|combinado\s+com)\s+art(?:igo)?s?\b\.?\s*\d+[^,.;\n]*)*"
            r"(?:\s+(?:do\s+CP|do\s+C[oó]digo\s+Penal|da\s+Lei[^\n,.;]*))?",
            re.IGNORECASE,
        )
        for a in penal_rx.findall(denuncia_text):
            a_clean = a.strip(" ,.;")
            if a_clean and a_clean not in all_articles and not is_procedural_or_constitutional(a_clean, denuncia_text):
                all_articles.append(a_clean)

        # Special laws (ECA, Drogas, Armamento, Maria da Penha, CTB)
        law_rx = re.compile(
            r"\b(?:Lei\s+(?:n[º°\.]?\s*)?[\d\./]+|ECA|Lei\s+Maria\s+da\s+Penha|Estatuto\s+do\s+Desarmamento|Lei\s+de\s+Drogas)"
            r"(?:\s*\([^\)]+\))?(?:\s*,\s*art(?:igo)?\.?\s*\d+[^;.\n]*)?",
            re.IGNORECASE,
        )
        for l in law_rx.findall(denuncia_text):
            l_clean = l.strip(" ,.;")
            if l_clean and l_clean not in all_articles and not is_procedural_or_constitutional(l_clean, denuncia_text):
                all_articles.append(l_clean)

        # Crime concurrence (arts. 69, 70, 71 do CP - only substantive CP, NEVER CPP!)
        concurso_rx = re.compile(
            r"\bart[s]?\.?\s*(?:69|70|71)\b[^\n,.;)]*(?:do\s+CP|do\s+C[oó]digo\s+Penal)?",
            re.IGNORECASE,
        )
        for c in concurso_rx.findall(denuncia_text):
            c_clean = c.strip(" ,.;)")
            if c_clean and c_clean not in all_articles and not is_procedural_or_constitutional(c_clean, denuncia_text):
                all_articles.append(c_clean)

        if base_imputation:
            base_imputation = re.sub(r"^[:\s\d\.\)\-]+", "", base_imputation).strip()
            final_imp = base_imputation
            # Supplement key missing substantive elements (e.g. corruption of minors / ECA)
            for art in all_articles:
                if ("244" in art or "eca" in art.lower()) and ("244" not in final_imp and "eca" not in final_imp.lower()):
                    final_imp += f" c/c {art}"
            return annotate_imputation_text(final_imp)

        if all_articles:
            unique_articles = []
            seen_clean = set()
            for art in all_articles:
                norm = re.sub(r"\s+", " ", art).replace("§ ", "§").strip().lower()
                if norm not in seen_clean:
                    seen_clean.add(norm)
                    unique_articles.append(art)
            joined = " c/c ".join(unique_articles) if len(unique_articles) <= 4 else ", ".join(unique_articles)
            return annotate_imputation_text(joined)

        return "Artigo de lei a ser apurado"
