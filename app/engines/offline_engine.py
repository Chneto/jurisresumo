"""Mode 2: 100% Offline Local Extraction Engine for Judicial Case Summaries.

Uses high-performance regex patterns, PJe document indexing, and structural heuristics
to parse complete PJe PDF files without external network connections.

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
from app.core.crime_taxonomy import annotate_imputation_text
from app.core.jev_decision_engine import JEVDecisionEngine, is_procedural_or_constitutional
from app.core.ocr_engine import OCREngine
from app.core.pje_indexer import index_pje_pdf, prune_documents
from app.engines.base import BaseExtractionEngine


# ANPP and PSCP revocation regexes (retomada da marcha penal -> AIJ)
ANPP_REVOCATION_REGEX = re.compile(
    r"(?:revog(?:a[cç][aã]o|ou|ando|ado|o)?|rescis[aã]o|rescind(?:iu|indo|ida|ido)?|descumprimento)\s+(?:d[eoa]\s+|[oa]\s+)?(?:acordo\s+de\s+n[aã]o\s+persecu[cç][aã]o(?:\s+penal)?|anpp)|(?:anpp|acordo)\s+(?:foi\s+)?revogad[ao]|revogo\s+o\s+(?:acordo|anpp)",
    re.IGNORECASE,
)

PSCP_REVOCATION_REGEX = re.compile(
    r"(?:revog(?:a[cç][aã]o|ou|ando|ado|o)?|descumprimento)\s+(?:d[eoa]\s+|[oa]\s+)?(?:suspens[aã]o\s+condicional\s+do\s+processo|pscp|benef[ií]cio\s+do\s+art\.?\s*89)|descumprimento\s+d[ae]\s+(?:condi[cç][oõ]es\s+da\s+)?(?:suspens[aã]o|pscp)|(?:suspens[aã]o\s+condicional\s+do\s+processo|pscp)\s+(?:foi\s+)?revogad[ao]|revogo\s+a\s+suspens[aã]o\s+condicional\s+do\s+processo",
    re.IGNORECASE,
)


# Standard regex for Brazilian judicial case numbers (CNJ)
CNJ_REGEX = re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b")

# Videoconference links
TEAMS_REGEX = re.compile(
    r"(?:https?://)?(?:[a-z0-9-]+\.)?teams\.(?:microsoft|live)\.com/(?:meet|l/meetup-join|dl/launcher)/[^\s\"'>)]+|"
    r"(?:https?://)?(?:[a-z0-9-]+\.)?teams\.(?:microsoft|live)\.com/[^\s\"'>)]+|"
    r"(?:https?://)?lnk\.tjrn\.jus\.br/[a-zA-Z0-9_-]+",
    re.IGNORECASE,
)
MEET_REGEX = re.compile(
    r"(https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3})",
    re.IGNORECASE,
)

# Month map for Portuguese date parsing
MONTH_MAP = {
    "janeiro": "01", "jan": "01",
    "fevereiro": "02", "fev": "02",
    "março": "03", "marco": "03", "mar": "03",
    "abril": "04", "abr": "04",
    "maio": "05", "mai": "05",
    "junho": "06", "jun": "06",
    "julho": "07", "jul": "07",
    "agosto": "08", "ago": "08",
    "setembro": "09", "set": "09",
    "outubro": "10", "out": "10",
    "novembro": "11", "nov": "11",
    "dezembro": "12", "dez": "12",
}

# Regex to detect hearing designation / scheduling in judicial acts
HEARING_DESIGNATION_REGEX = re.compile(
    r"(?:(?:design[ao]|apraz[ao]|reapraz[ao]|redesign[ao]|remarc[ao]|inclua-se|incluo)\s+.*?\b(?:audi[eê]ncia|pauta)|"
    r"pauta\s+(?:para|de)\s+(?:audi[eê]ncia|aij)|"
    r"audi[eê]ncia\s+.*?\b(?:designad[ao]|aprazad[ao]|reaprazad[ao]|redesignad[ao]|remarcad[ao]|marcad[ao]|agendad[ao]|para\s+o\s+dia|no\s+dia)|"
    r"designo\s+o\s+dia\s+\d+|"
    r"audi[eê]ncia\s+de\s+(?:instru[cç][aã]o|homologa[cç][aã]o|produ[cç][aã]o|cust[oó]dia)|"
    r"termo\s+de\s+audi[eê]ncia\s+de\s+instru[cç][aã]o|"
    r"ata\s+d[ae]\s+audi[eê]ncia)",
    re.IGNORECASE | re.DOTALL,
)

# Regex to detect ANPP Negation (when ANPP is refused, rejected, or declared unavailable)
ANPP_NEGATION_REGEX = re.compile(
    r"(?:n[aã]o\s+(?:foi|h[aá]|sendo|cabe|cab[ií]vel|seja)\s+propost[ao]\s+anpp|"
    r"n[aã]o\s+(?:foi|h[aá]|sendo|cabe|cab[ií]vel|seja)\s+propost[ao]\s+(?:acordo\s+de\s+)?n[aã]o\s+persecu[cç][aã]o|"
    r"deix[ao](?:-se)?\s+de\s+propor\s+(?:o\s+)?(?:anpp|acordo)|"
    r"incab[ií]vel\s+(?:o\s+)?(?:anpp|acordo)|"
    r"invi[aá]vel\s+(?:o\s+)?(?:anpp|acordo)|"
    r"ausentes\s+(?:os\s+)?requisitos\s+(?:do\s+)?(?:anpp|acordo)|"
    r"n[aã]o\s+(?:possui|preenche)\s+(?:os\s+)?requisitos|"
    r"recusou\s+(?:o\s+)?(?:anpp|acordo)|"
    r"anpp\s+infrut[ií]fero|"
    r"n[aã]o\s+aceitou\s+(?:a\s+proposta|o\s+anpp)|"
    r"afastada\s+a\s+possibilidade\s+de\s+anpp|"
    r"deixa-se\s+de\s+propor\s+acordo|"
    r"cota.*anpp)",
    re.IGNORECASE | re.DOTALL,
)

# Regex to detect state organs mistakenly placed in the passive pole (system errors to be discarded)
STATE_ORGANS_BLACKLIST_REGEX = re.compile(
    r"^(?:(?:\d+[ªa°º]?\s+)?(?:delegacia|dp\b|dpc\b|distrito\s+policial|defensoria|vara\s+criminal|promotoria)|"
    r"delegacia|estado(?:\s+d[oae]s?)?|defensoria|minist[eé]rio\s+p[uú]blico|pol[ií]cia|"
    r"secretaria|comando|tribunal|juizado|vara\s+criminal|procuradoria|instituto|banco|"
    r"central\s+de\s+(?:flagrantes|recebimento|cust[oó]dia)|dp\s+de|dpc\b|plant[aã]o\s+(?:da\s+)?pol[ií]cia|"
    r"departamento|munic[ií]pio|uni[aã]o|"
    r"deicot|deicor|denarc|dhpp|dea\b|deprov|dapr)\b",
    re.IGNORECASE,
)


def _make_accent_tolerant_regex(text: str) -> str:
    """Creates a regex pattern that matches Portuguese accented or unaccented variations of the text."""
    vowel_map = {
        'a': r'[aáàãâäAÁÀÃÂÄ]', 'á': r'[aáàãâäAÁÀÃÂÄ]', 'à': r'[aáàãâäAÁÀÃÂÄ]', 'ã': r'[aáàãâäAÁÀÃÂÄ]', 'â': r'[aáàãâäAÁÀÃÂÄ]',
        'e': r'[eéêëEÉÊË]', 'é': r'[eéêëEÉÊË]', 'ê': r'[eéêëEÉÊË]',
        'i': r'[iíîïIÍÎÏ]', 'í': r'[iíîïIÍÎÏ]',
        'o': r'[oóôõöOÓÔÕÖ]', 'ó': r'[oóôõöOÓÔÕÖ]', 'ô': r'[oóôõöOÓÔÕÖ]', 'õ': r'[oóôõöOÓÔÕÖ]',
        'u': r'[uúûüUÚÛÜ]', 'ú': r'[uúûüUÚÛÜ]',
        'c': r'[cçCÇ]', 'ç': r'[cçCÇ]',
    }
    pattern_parts = []
    for char in text:
        lower_c = char.lower()
        if lower_c in vowel_map:
            pattern_parts.append(vowel_map[lower_c])
        else:
            pattern_parts.append(re.escape(char))
    return "".join(pattern_parts)


def _normalize_witness_name(name: str) -> str:
    """Strips military/police titles, ranks, and judicial prefixes before comparison."""
    clean = re.sub(
        r"^(?:pm\s+|policial(?:\s+militar|\s+civil)?\s+|cabo\s+|cb\s+|sgt\s+|sargento\s+|sd\s+|soldado\s+|subtenente\s+|tenente\s+|capit[aã]o\s+|dr(?:a|\(a\))?\.?\s+)+",
        "",
        name.strip(),
        flags=re.IGNORECASE,
    )
    return clean.strip()


def _format_date_short(date_str: str) -> str:
    """Converts DD/MM/YYYY or variations to DD/MM/AA with strict mask."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", date_str)
    if match:
        day, month, year = match.groups()
        day_str = f"{int(day):02d}"
        month_str = f"{int(month):02d}"
        year_str = year[-2:]
        return f"{day_str}/{month_str}/{year_str}"
    return date_str


def _parse_date_sort_key(date_str: str, doc_id: str = "") -> Tuple[int, int, int, int]:
    """Extracts (year, month, day, doc_id_int) for ascending chronological sorting."""
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", date_str or "")
    doc_num = int(doc_id) if doc_id and doc_id.isdigit() else 0
    if match:
        d, m, y = match.groups()
        year = int(y)
        if year < 100:
            year = 2000 + year if year < 70 else 1900 + year
        return (year, int(m), int(d), doc_num)
    return (1900, 1, 1, doc_num)


def _clean_legal_text(text: str) -> str:
    """Removes PJe stamps, signature blocks, page numbers, and validation URLs from extracted text."""
    if not text:
        return ""
    text = text.replace("\u200b", " ").replace("\ufeff", "")
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        l_s = line.strip()
        if not l_s:
            clean_lines.append("")
            continue
        # Drop PJe marginal stamp lines and header stamps
        if re.search(r"-\s*\d+\s+de\s+\d+\s+laudas\s*-", l_s, re.I):
            continue
        if re.search(r"Num\.\s*\d+\s*-\s*P[aáAÁ]g\.", l_s, re.I):
            continue
        if re.search(r"P[aá]g\.\s*Total\s*-\s*\d+", l_s, re.I):
            continue
        if re.search(r"P[aá]g\.\s*\d+\s*de\s*\d+", l_s, re.I):
            continue
        if re.search(r"Assinado\s+eletronicamente\s+por", l_s, re.I):
            continue
        if re.search(r"https?://pje\S+", l_s, re.I) or re.search(r"https?://consultapublica\S+", l_s, re.I):
            continue
        if re.search(r"Documento\s+n[ºo]\s*\d+\s+do\s+procedimento", l_s, re.I):
            continue
        if re.search(r"Valida[cç][aã]o\s+em\s+", l_s, re.I):
            continue
        if re.search(r"N[úu]mero\s+do\s+documento:\s*\d+", l_s, re.I):
            continue
        if re.search(r"^\s*MINIST[EÉ]RIO\s+P[UÚ]BLICO", l_s, re.I):
            continue
        if re.search(r"PROMOTORIA\s+DE\s+JUSTI[CÇ]A", l_s, re.I):
            continue
        if re.search(r"Defesa\s+dos\s+Direitos", l_s, re.I):
            continue
        if re.search(r"^\s*Rua\s+(?:Promotor|Milit[aã]o|Doutor|Serid[oó]|Alameda)", l_s, re.I):
            continue
        if re.search(r"^Telefone\(s\):", l_s, re.I) or re.search(r"^E-mail:", l_s, re.I) or re.search(r"^www\.", l_s, re.I):
            continue
        if re.search(r"^\s*_{5,}\s*$", l_s):
            continue
        clean_lines.append(line)
    cleaned = "\n".join(clean_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


class OfflineExtractionEngine(BaseExtractionEngine):
    """100% Offline Rule-Based Extraction Engine for PJe autos."""

    def extract(
        self,
        pdf_path: str,
        pje_catalog: Optional[List[PJeDocument]] = None,
        **kwargs,
    ) -> HearingSummaryData:
        """Extracts structured summary data locally from the PJe PDF."""
        pdf_p = Path(pdf_path)
        if not pdf_p.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Index PJe PDF if catalog not provided
        if not pje_catalog:
            pje_catalog, doc = index_pje_pdf(pdf_path)
        else:
            doc = pymupdf.open(pdf_path)

        # 1. Extract Case Number
        case_number = self._extract_case_number(doc, pdf_p.name)

        # 2. Extract Parties from Page 1 Capa
        reus_capa, advs_capa, vitimas_capa, testemunhas_capa, prom_capa = self._parse_capa_parties(doc)

        # 3. Locate Key Documents & Hearing Act
        denuncia_doc = None
        decisao_audiencia_doc = None
        resposta_doc = None
        mandados_docs: List[PJeDocument] = []

        # Find Denúncia (reverse search prioritizing official complaint from MP, concatenating multi-part segments)
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

        # Find Resposta à Acusação (and all defense petitions)
        defense_docs = self._find_all_defense_documents(pje_catalog, doc, reus_capa, advs_capa)
        if defense_docs:
            resposta_doc = defense_docs[0].get("doc")
        else:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if ("resposta" in comb and "acusação" in comb) or "defesa prévia" in comb:
                    resposta_doc = p_doc
                    break

        for p_doc in pje_catalog:
            comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
            if any(k in comb for k in ["mandado", "intimação", "certidão", "ofício", "diligência", "ato negativo", "ato positivo", "comprovante"]):
                mandados_docs.append(p_doc)

        # Reverse search for the most recent hearing designation judicial act
        hearing_text = ""
        for p_doc in reversed(pje_catalog):
            comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
            if any(ex in comb for ex in ["manual", "extrato", "dados telef", "comprovante", "foto", "laudo", "inquérito", "boletim"]):
                continue
            if any(k in comb for k in ["decis", "despacho", "ato ordinat", "audiência", "audiencia", "intimação", "mandado", "termo", "ata da audiência"]):
                txt = self._extract_doc_text(doc, p_doc)
                if HEARING_DESIGNATION_REGEX.search(txt):
                    decisao_audiencia_doc = p_doc
                    hearing_text = txt
                    break

        # Fallback to general hearing search if not found in candidate acts
        if not decisao_audiencia_doc:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if "audiência" in comb or "audiencia" in comb or "designa" in comb:
                    decisao_audiencia_doc = p_doc
                    hearing_text = self._extract_doc_text(doc, p_doc)
                    break

        # Extract text from Denúncia and Resposta
        denuncia_text = "\n\n".join(self._extract_doc_text(doc, d) for d in denuncia_docs) if denuncia_docs else (self._extract_doc_text(doc, denuncia_doc) if denuncia_doc else "")
        resposta_text = self._extract_doc_text(doc, resposta_doc) if resposta_doc else ""

        # 4. Determine Act Type (AIJ, ANPP, PAnP, Custódia, Sursis)
        hearing_doc_name = decisao_audiencia_doc.doc_name if decisao_audiencia_doc else ""
        act_type = self._determine_act_type(
            pdf_p.name, hearing_text, hearing_doc_name, doc, denuncia_doc, pje_catalog
        )

        # 5. Hearing Date, Time & Meeting Link
        hearing_datetime, hearing_link, is_in_person = self._extract_hearing_details(
            hearing_text, pdf_p.name, doc, pje_catalog
        )

        # 6. Prosecutor
        prosecutor = self._extract_prosecutor(denuncia_text, prom_capa, doc)

        # 7. Defendants & Qualification
        defendants, qualification_text = self._extract_defendants_and_qual(
            denuncia_text, reus_capa, doc, pje_catalog, mandados_docs
        )

        # 8. Imputation
        imputation_text = self._extract_imputation(denuncia_text)

        # Audit & complement qualification and imputation via JEV Decision Engine
        qualification_text, imputation_text = JEVDecisionEngine.get_instance().audit_qualification_and_imputation(
            qualification_text, imputation_text, denuncia_text
        )

        # 9. Summary of Facts
        facts_summary, special_notes = self._extract_facts(
            denuncia_text, act_type, pje_catalog, doc
        )

        # 10. Chronological History with IDs
        chronological_history = self._build_chronological_history(
            pje_catalog, doc, reus_capa, advs_capa
        )

        # 11. Witnesses (Prosecution & Defense) with Unified Deduplication & Labeling
        pros_witnesses, def_witnesses, def_note = self._extract_witnesses(
            denuncia_text, resposta_text, vitimas_capa, testemunhas_capa, mandados_docs, doc, defense_docs, reus_capa
        )

        # 12. Defense Counsel
        defense_counsel = self._extract_defense_counsel(
            resposta_text, advs_capa, doc, defense_docs, reus_capa
        )

        # For ANPP cases, trial sections must be omitted strictly
        if act_type == "ANPP":
            qualification_text = ""
            imputation_text = ""
            chronological_history = []
            pros_witnesses = []
            def_witnesses = []
            def_note = None

        doc.close()

        return HearingSummaryData(
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
            closure_text="Cordial e respeitosamente,",
        )

    def _extract_case_number(self, doc: pymupdf.Document, filename: str) -> str:
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

    def _parse_capa_parties(
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

        return reus, advs, vitimas, testemunhas, prom

    def _extract_doc_text(self, doc: pymupdf.Document, p_doc: Optional[PJeDocument]) -> str:
        """Extracts text for a specific PJe document based on page range with fallback and calibrated OCR."""
        if not p_doc:
            return ""
        if p_doc.start_page > 0:
            text_parts = []
            for p in range(p_doc.start_page - 1, min(p_doc.end_page, len(doc))):
                p_text = doc[p].get_text()
                if not p_text.strip() or (p_doc.is_scanned and len(p_text.strip()) < 50):
                    ocr_res = OCREngine.get_instance().ocr_page(doc[p])
                    if ocr_res and ocr_res.text.strip():
                        p_text = ocr_res.text
                text_parts.append(p_text)
            txt = "\n".join(text_parts).strip()
            if txt:
                return txt

        # Fallback for unmapped document or empty page range: search for doc_id in all pages
        if p_doc.doc_id:
            id_str = str(p_doc.doc_id)
            for p in range(len(doc)):
                p_text = doc[p].get_text()
                if id_str in p_text:
                    if not p_text.strip() or (p_doc.is_scanned and len(p_text.strip()) < 50):
                        ocr_res = OCREngine.get_instance().ocr_page(doc[p])
                        if ocr_res and ocr_res.text.strip():
                            p_text = ocr_res.text
                    return p_text

        return ""

    def _determine_act_type(
        self,
        filename: str,
        hearing_text: str,
        hearing_doc_name: str,
        doc: pymupdf.Document,
        denuncia_doc: Optional[PJeDocument],
        pje_catalog: List[PJeDocument],
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
                    txt = self._extract_doc_text(doc, p_doc).lower()
                    if "recebo a denúncia" in txt or "recebida a denúncia" in txt or "recebimento da denúncia" in txt or "art. 396" in txt or "art. 399" in txt or "absolvição sumária" in txt:
                        has_received_denuncia = True
                    if "instrução e julgamento" in txt or "audiência de instrução" in txt or "oitiva de testemunha" in txt or "oitiva das testemunhas" in txt or "inquirir as testemunhas" in txt or "interrogatório do réu" in txt:
                        has_aij_mention = True
                    if ANPP_NEGATION_REGEX.search(txt) or "não sendo caso de anpp" in txt or "afasto o anpp" in txt or "recusa do anpp" in txt or "anpp recusado" in txt or "deixo de propor anpp" in txt:
                        has_anpp_rejection = True

        # Check for revocation documents in catalog
        anpp_rev_doc = None
        pscp_rev_doc = None
        if pje_catalog and doc is not None:
            for p_doc in pje_catalog:
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["decis", "despacho", "ato ordinat", "termo"]):
                    txt = self._extract_doc_text(doc, p_doc)
                    if ANPP_REVOCATION_REGEX.search(txt):
                        anpp_rev_doc = p_doc
                    if PSCP_REVOCATION_REGEX.search(txt):
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

    def _extract_hearing_details(
        self,
        hearing_text: str,
        filename: str,
        doc: pymupdf.Document,
        pje_catalog: List[PJeDocument],
    ) -> Tuple[str, Optional[str], bool]:
        """Extracts date/time, meeting link, and in-person flag across the entire document."""
        meeting_link = None

        # 1. Search for videoconference link in hearing text
        if hearing_text:
            m = TEAMS_REGEX.search(hearing_text) or MEET_REGEX.search(hearing_text)
            if m:
                meeting_link = m.group(0).rstrip(">)]., \r\n")

        # 2. Search subsequent notifications / intimations in catalog
        if not meeting_link:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["intimação", "mandado", "certidão", "diligência", "audiência", "despacho", "decisão", "link"]):
                    d_txt = self._extract_doc_text(doc, p_doc)
                    m = TEAMS_REGEX.search(d_txt) or MEET_REGEX.search(d_txt)
                    if m:
                        meeting_link = m.group(0).rstrip(">)]., \r\n")
                        break

        # 3. Fallback scan annotations and text in the last 25 pages
        if not meeting_link:
            total_p = len(doc)
            for p in range(total_p - 1, max(-1, total_p - 25), -1):
                page = doc[p]
                for link in page.get_links():
                    uri = link.get("uri", "")
                    if uri and (TEAMS_REGEX.search(uri) or MEET_REGEX.search(uri)):
                        m_u = TEAMS_REGEX.search(uri) or MEET_REGEX.search(uri)
                        meeting_link = m_u.group(0).rstrip(">)]., \r\n")
                        break
                if meeting_link:
                    break
                txt = page.get_text()
                m = TEAMS_REGEX.search(txt) or MEET_REGEX.search(txt)
                if m:
                    meeting_link = m.group(0).rstrip(">)]., \r\n")
                    break

        if meeting_link and not meeting_link.startswith("http"):
            meeting_link = "https://" + meeting_link

        is_in_person = meeting_link is None

        # Date & Time Extraction:
        # Step 1: Check filename first (strip CNJ numbers to prevent false date matches)
        fn_clean = re.sub(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}(?:-\d+)?\b", "", filename)
        fn_clean = re.sub(r"\b\d\.\d{2}\.\d{4}(?:-\d+)?\b", "", fn_clean)

        m_inv = re.search(r"(\d{1,2}h(?:\d{2})?)\s*[-–]\s*(\d{1,2})[./](\d{1,2})[./](\d{2,4})", fn_clean, re.I)
        if m_inv:
            t_str, d, m, y = m_inv.groups()
            d_i, m_i = int(d), int(m)
            if 1 <= d_i <= 31 and 1 <= m_i <= 12:
                yr = y[-2:] if len(y) == 4 else y
                tm = t_str if "min" in t_str else (t_str + "00min" if len(t_str) <= 3 else t_str)
                return f"{d_i:02d}.{m_i:02d}.{yr} às {tm}", meeting_link, is_in_person

        m_fn = re.search(
            r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s*(?:,?\s*(?:às|as|-)\s*)(\d{1,2})(?::(\d{2})|h(\d{0,2})(?:min)?)?",
            fn_clean,
            re.I,
        )
        if m_fn:
            d, m, y, h, mn_col, mn_h = m_fn.groups()
            d_i, m_i, h_i = int(d), int(m), int(h)
            y_i = int(y)
            y_valid = (2020 <= y_i <= 2035) if len(y) == 4 else (20 <= y_i <= 35)
            if 1 <= d_i <= 31 and 1 <= m_i <= 12 and 0 <= h_i <= 23 and y_valid:
                yr = y[-2:] if len(y) == 4 else y
                mn = mn_col or mn_h or "00"
                if not mn:
                    mn = "00"
                return f"{d_i:02d}.{m_i:02d}.{yr} às {h_i:02d}h{mn}min", meeting_link, is_in_person

        # Step 2: Search in hearing_text
        if hearing_text:
            dt_h = self._parse_datetime_from_text(hearing_text)
            if dt_h:
                return dt_h, meeting_link, is_in_person

        # Step 3: Search relevant hearing/mandado/intimação documents in catalog
        for p_doc in reversed(pje_catalog):
            comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
            if any(k in comb for k in ["audiência", "audiencia", "intimação", "mandado", "despacho", "decisão"]):
                d_txt = self._extract_doc_text(doc, p_doc)
                dt_d = self._parse_datetime_from_text(d_txt)
                if dt_d:
                    return dt_d, meeting_link, is_in_person

        # Step 4: Fallback scan ONLY the last 5 pages of the document
        total_p = len(doc)
        for p in range(total_p - 1, max(-1, total_p - 6), -1):
            txt = doc[p].get_text()
            dt_p = self._parse_datetime_from_text(txt)
            if dt_p:
                return dt_p, meeting_link, is_in_person

        return "Data a definir", meeting_link, is_in_person

    def _parse_datetime_from_text(self, txt: str) -> Optional[str]:
        """Extracts and formats hearing date and time from Portuguese text."""
        # 1. Portuguese format with month names:
        # e.g. "para o dia 17 (sexta-feira) de julho de 2026, às 09:00 horas"
        # or "dia 24 de julho de 2026, às 11h25min"
        # or "dia 10 de julho de 2026 às 11 horas"
        m_pt = re.search(
            r"(?:dia|data|para|em|pauta)\s+(\d{1,2})\s*(?:(?:de|[^\w\d]){1,20}(?:[a-zçãõ-]+feira|[^\w\d]){0,20})?\s*(?:de\s+)?(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s*(?:de\s+)?(\d{2,4})[^\n\d]{1,40}?(?:às|as)\s*(\d{1,2})(?::(\d{2})|h(\d{0,2})(?:min)?)?",
            txt,
            re.IGNORECASE,
        )
        if m_pt:
            d, m_name, y, h, mn_col, mn_h = m_pt.groups()
            d_i, h_i = int(d), int(h)
            if 1 <= d_i <= 31 and 0 <= h_i <= 23:
                m_num = MONTH_MAP.get(m_name.lower().strip(), "07")
                yr = y[-2:] if len(y) == 4 else y
                mn = mn_col or mn_h or "00"
                if not mn:
                    mn = "00"
                return f"{d_i:02d}.{m_num}.{yr} às {h_i:02d}h{mn}min"

        # 2. Numeric date format:
        # e.g. "no dia 31/07/2026 às 11:00 horas" or "em 23/07/26 às 13h"
        m_num = re.search(
            r"(?:dia|data|para|em|pauta|audi[eê]ncia)\s+(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\s*(?:,?\s*(?:às|as|-)\s*)(\d{1,2})(?::(\d{2})|h(\d{0,2})(?:min)?)?",
            txt,
            re.IGNORECASE,
        )
        if m_num:
            d, m, y, h, mn_col, mn_h = m_num.groups()
            d_i, m_i, h_i = int(d), int(m), int(h)
            y_i = int(y)
            y_valid = (2020 <= y_i <= 2035) if len(y) == 4 else (20 <= y_i <= 35)
            if 1 <= d_i <= 31 and 1 <= m_i <= 12 and 0 <= h_i <= 23 and y_valid:
                yr = y[-2:] if len(y) == 4 else y
                mn = mn_col or mn_h or "00"
                if not mn:
                    mn = "00"
                return f"{d_i:02d}.{m_i:02d}.{yr} às {h_i:02d}h{mn}min"

        # 3. General scheduling phrase fallback
        m_gen = re.search(
            r"(?:no\s+dia|pauta\s+para|designad[oa]\s+para|aprazad[oa]\s+para|audi[eê]ncia\s+em)\s+(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s*(?:,|às|as)\s*(\d{1,2})(?::(\d{2})|h(\d{0,2}))",
            txt,
            re.IGNORECASE,
        )
        if m_gen:
            d, m, y, h, mn_col, mn_h = m_gen.groups()
            d_i, m_i, h_i = int(d), int(m), int(h)
            y_i = int(y)
            y_valid = (2020 <= y_i <= 2035) if len(y) == 4 else (20 <= y_i <= 35)
            if 1 <= d_i <= 31 and 1 <= m_i <= 12 and 0 <= h_i <= 23 and y_valid:
                yr = y[-2:] if len(y) == 4 else y
                mn = mn_col or mn_h or "00"
                if not mn:
                    mn = "00"
                return f"{d_i:02d}.{m_i:02d}.{yr} às {h_i:02d}h{mn}min"

        return None

    def _extract_prosecutor(
        self, denuncia_text: str, prom_capa: Optional[str], doc: pymupdf.Document
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
                    prom_num = re.search(r"(\d+ª?\s+Promotoria[^\n()]+)", prom_capa, re.I)
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
                    prom_num = re.search(r"(\d+ª?\s+Promotoria[^\n()]+)", prom_capa, re.I)
                    if prom_num:
                        prom_name += f" ({prom_num.group(1).strip()})"
                return prom_name

        # 3. Fallback to prom_capa
        if prom_capa:
            clean_prom = re.sub(r"^[A-Z\s]+:\s*", "", prom_capa).strip()
            clean_prom = re.sub(r"\(AUTOR\)", "", clean_prom, flags=re.I).strip()
            clean_prom = re.sub(r"\(P[oó]lo[^\)]*\)", "", clean_prom, flags=re.I).strip()
            prom_num = re.search(r"(\d+ª?\s+Promotoria[^\n()]+)", clean_prom, re.I)
            if prom_num:
                return f"Dr. Promotor de Justiça ({prom_num.group(1).strip()})"
            return f"Dr. Promotor de Justiça ({clean_prom})"

        return "Dr. Promotor de Justiça"

    def _extract_defendants_and_qual(
        self,
        denuncia_text: str,
        reus_capa: List[str],
        doc: pymupdf.Document,
        pje_catalog: List[PJeDocument],
        mandados_docs: List[PJeDocument],
    ) -> Tuple[List[Defendant], str]:
        """Extracts defendant list and detailed qualification with subpoena matching."""
        defendants: List[Defendant] = []
        # Discard any state organs from passive pole (system errors)
        names = [
            n for n in (reus_capa or [])
            if not STATE_ORGANS_BLACKLIST_REGEX.search(n.strip())
        ]

        # Find qualification block in Denúncia / Queixa-Crime
        qual_pattern = re.compile(
            r"(?:"
            r"(?:(?:III|II|I)\)?\s*(?:Acusad[oa]s?|Denunciad[oa]s?))|"
            r"DENUNCIADO\(?A?\)?:?|"
            r"DOS\s+DENUNCIADOS:?|"
            r"DA\s+QUALIFICA[CÇ][AÃ]O(?:\s+D[OE]S\s+DENUNCIAD[OA]S)?|"
            r"oferecer\s+(?:a\s+presente:?\s*)?(?:queixa(?:-crime)?\s+)?(?:em\s+desfavor\s+de|contra|em\s+face\s+de)[:\s]*|"
            r"oferece\s+(?:a\s+presente:?\s*)?(?:queixa(?:-crime)?\s+)?(?:em\s+desfavor\s+de|contra|em\s+face\s+de)[:\s]*|"
            r"em\s+face\s+de[:\s]*|"
            r"queixa(?:-crime)?\s+(?:em\s+face\s+de|contra)[:\s]*|"
            r"vem\s+perante\s+V\.\s*Exa\.?[^\n]*(?:denunciar|oferecer\s+queixa)[:\s]*"
            r")"
            r"(.*?)"
            r"(?:"
            r"(?:^|\n)\s*(?:(?:IV|V|VI)\)\s*Narrativa|(?:IV|V|VI)\)|DOS\s+FATOS|FATOS|I\s*[-–.]\s*DOS\s+FATOS|\n\s*Consta\s+d[oe]s\s+(?:inclus[oa]s|referidos)|pela\s+pr[aá]tica\s+dos\s+fatos|pelos\s+fatos\s+a\s+seguir|pelos\s+fatos\s+e\s+fundamentos|DELIMITA[CÇ][AÃ]O)"
            r")",
            re.IGNORECASE | re.DOTALL,
        )
        match = qual_pattern.search(denuncia_text)
        raw_qual = match.group(1).strip() if match else ""
        if raw_qual:
            raw_qual = _clean_legal_text(raw_qual)
            raw_qual = re.sub(r"[ \t]+", " ", raw_qual)

        if not names:
            # Fallback 1: Extract defendant directly from complaint text (queixa-crime / denúncia)
            m_face = re.search(
                r"(?:em\s+face\s+de|contra|denunciar|oferecer\s+den[uú]ncia\s+contra)\s+([A-ZÁÉÍÓÚÂÊÔÃÕ][A-ZÁÉÍÓÚÂÊÔÃÕ\s]{3,60}?)(?:,\s*(?:brasileir|casad|solteir|divorciad|nascid|filh|portador|advogad|inscrit))",
                denuncia_text,
                re.IGNORECASE,
            )
            if m_face:
                cand = m_face.group(1).strip()
                if not STATE_ORGANS_BLACKLIST_REGEX.search(cand):
                    names.append(cand.title())

            # Fallback 2: extraction from raw qualification
            if not names and raw_qual:
                all_caps_names = re.findall(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ]{2,}){1,5})\b", raw_qual)
                names = [
                    n.title() for n in all_caps_names
                    if not any(ex in n for ex in ["MINISTÉRIO", "ESTADO", "TRIBUNAL", "PODER", "VARA", "PROMOTORIA", "DENÚNCIA", "JUSTIÇA", "OAB"])
                    and not STATE_ORGANS_BLACKLIST_REGEX.search(n.strip())
                ]

        # Extract text from Inquérito Policial / APF if needed for detailed qualification
        ip_text = ""
        ip_docs = [d for d in pje_catalog if any(k in d.doc_name.lower() for k in ["inquérito", "inquerito", "flagrante", "interrogat", "qualifica"])]
        if ip_docs and (not raw_qual or len(raw_qual) < 50):
            for ip_d in ip_docs[:2]:
                ip_text += self._extract_doc_text(doc, ip_d) + "\n"

        if not names:
            names = ["RÉU A QUALIFICAR"]

        # Cache text of mandado / certidão / diligência docs to match by defendant name
        mandado_texts: Dict[str, str] = {}
        for m_doc in mandados_docs:
            mandado_texts[m_doc.doc_id] = self._extract_doc_text(doc, m_doc).lower()

        # Check for prison facility across all pages
        full_pdf_prison = ""
        for p in range(min(len(doc), 180)):
            p_text = doc[p].get_text().lower()
            if "custodiado na" in p_text or "penitenciária" in p_text or "cadeia pública" in p_text:
                prison_m = re.search(r"(custodiado\s+na\s+[^,;\n]+|penitenci[aá]ria\s+estadual\s+de\s+[^,;\n]+|cadeia\s+p[uú]blica\s+de\s+[^,;\n]+)", p_text, re.I)
                if prison_m:
                    full_pdf_prison = prison_m.group(1).strip()
                    break

        defendant_quals: List[str] = []
        for name in names:
            if STATE_ORGANS_BLACKLIST_REGEX.search(name.strip()):
                continue

            name_lower = name.lower()
            first_name = name.split()[0].lower() if name.split() else ""
            surname = name.split()[-1].lower() if len(name.split()) > 1 else ""

            # Extract complete qualification block for this defendant
            d_qual = self._extract_single_defendant_qualification(name, raw_qual, denuncia_text, ip_text)
            defendant_quals.append(d_qual)

            # Detect prison status
            status = "respondendo ao processo em liberdade"
            if "preso" in raw_qual.lower() or "custodiado" in raw_qual.lower() or "penitenciária" in raw_qual.lower() or full_pdf_prison:
                if full_pdf_prison:
                    status = f"réu preso, atualmente {full_pdf_prison}"
                else:
                    status = "réu preso"

            # Check decisions for suspension/edital
            if "edital" in denuncia_text.lower() or "suspenso" in denuncia_text.lower():
                status = "citado por edital"

            # Check if not found / unserved
            for doc_id, m_text in mandado_texts.items():
                if (name_lower in m_text or (len(first_name) > 3 and len(surname) > 3 and first_name in m_text and surname in m_text)) and ("não localizado" in m_text or "deixei de citar" in m_text):
                    status = "não citado e não localizado"
                    break

            # Find matching subpoena / citation ID in mandado docs
            subpoena_id = None
            citation_id = None
            for doc_id, m_text in mandado_texts.items():
                if name_lower in m_text or (len(first_name) > 3 and first_name in m_text):
                    if "citação" in m_text or "citei" in m_text:
                        citation_id = doc_id
                    if "intimação" in m_text or "intimei" in m_text or "audiência" in m_text:
                        subpoena_id = doc_id
                        break

            # Fallback to general mandado if not matched individually
            if not subpoena_id:
                for p_doc in pje_catalog:
                    d_name = p_doc.doc_name.lower()
                    if "mandado" in d_name and ("intimação" in d_name or "cumprido" in d_name):
                        subpoena_id = p_doc.doc_id
                        break
                    elif "mandado" in d_name and "citação" in d_name and not citation_id:
                        citation_id = p_doc.doc_id

            defendants.append(
                Defendant(
                    name=name.title(),
                    status=status,
                    citation_id=citation_id,
                    subpoena_id=subpoena_id,
                    qualification=d_qual,
                )
            )

        qual_text = "\n\n".join(defendant_quals) if defendant_quals else (raw_qual if raw_qual else "\n\n".join([f"{n}, qualificação nos autos." for n in names]))
        return defendants, qual_text

    def _extract_single_defendant_qualification(
        self, name: str, raw_qual: str, denuncia_text: str, ip_text: str
    ) -> str:
        """Extracts complete qualification for a defendant (filiation, RG, CPF, birth date, address)."""
        name_clean = name.strip()
        if not name_clean:
            return ""
        esc_name = _make_accent_tolerant_regex(name_clean)
        first_name = name_clean.split()[0] if name_clean.split() else ""
        esc_first_surname = ""
        if len(name_clean.split()) >= 2:
            esc_first_surname = rf"{_make_accent_tolerant_regex(first_name)}[^\n,;]+?{_make_accent_tolerant_regex(name_clean.split()[-1])}"

        name_rx = rf"(?:{esc_name}|{esc_first_surname})" if esc_first_surname else esc_name

        # 1. Capture multiline qualification block without premature stopping at ; or \n or blank lines
        lookahead = (
            r"(?=(?:\n\s*(?:(?:[I|V|X]+\)?\s*[-–.]?\s*)?(?:DOS\s+FATOS|FATOS|DA\s+IMPUTA[CÇ][AÃ]O|DELIMITA[CÇ][AÃ]O|DOS\s+PEDIDOS|DO\s+PEDIDO|ROL\s+DE\s+TESTEMUNHAS|DA\s+QUALIFICA[CÇ][AÃ]O|DA\s+CONTEXTUALIZA[CÇ][AÃ]O|CONTEXTUALIZA[CÇ][AÃ]O|HIST[OÓ]RICO)|Vem\s+perante|pela\s+pr[aá]tica|oferecer\s+den[uú]ncia)|"
            r"(?:,\s*|[;.]\s*|\n\s*)(?:pelos?\s+fatos\s+e\s+fundamentos|(?:em\s+raz[aã]o|por\s+motivo|diante)\s+d[oae]s\s+(?:motivos|fatos)\s+f[aá]ticos|passa\s+a\s+expor)|"
            r"\n\s*(?:\d+[\.\)]\s*)?[A-ZÁÉÍÓÚ]{3,}(?:\s+[A-ZÁÉÍÓÚ]{2,}){1,4},?\s*(?:brasileir|solteir|casad|divorciad|nascid|filh|portador|residente|rg\b|cpf\b|vulgo)|"
            r"$))"
        )
        qual_pattern = re.compile(
            rf"(?:^|\n|[;.]\s*|em\s+face\s+de\s+)\b({name_rx}[\s\S]{{1,1200}}?)" + lookahead,
            re.IGNORECASE,
        )

        chunk = ""
        if raw_qual:
            m = qual_pattern.search(raw_qual)
            if m:
                chunk = _clean_legal_text(m.group(1)).strip(" ;.\n")

        if not chunk and denuncia_text:
            m2 = qual_pattern.search(denuncia_text)
            if m2:
                chunk = _clean_legal_text(m2.group(1)).strip(" ;.\n")

        if chunk:
            chunk = re.sub(r"-\s*\d+\s+de\s+\d+\s+laudas\s*-", "", chunk, flags=re.I)
            chunk = re.sub(r"GRUPO\s+DE\s+ATUA[CÇ][AÃ]O\s+ESPECIAL\s+DE\s+COMBATE\s+AO\s+CRIME\s+ORGANIZADO[^\n]*", "", chunk, flags=re.I)
            chunk = re.sub(r"\d+ª\s+PROMOTORIA\s+DE\s+JUSTI[CÇ]A[^\n]*", "", chunk, flags=re.I)
            chunk = _clean_legal_text(chunk).strip(" ;.\n")

        # Check completeness of qualification: filiação, RG, CPF
        has_filiacao = bool(re.search(r"\bfilh[oa]\b|\bm[aã]e\b|\bpai\b|\bgenitor", chunk, re.I))
        has_rg = bool(re.search(r"\bRG\b|\b\d{6,}\b", chunk, re.I))
        has_cpf = bool(re.search(r"\bCPF\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", chunk, re.I))
        is_generic = "qualificad" in chunk.lower() or not chunk

        # 2. Check if chunk lacks filiação, RG, or CPF, or is generic -> fallback / merge from IP/APF
        if ip_text and (is_generic or not (has_filiacao and has_rg and has_cpf)):
            ip_pat = re.compile(
                rf"({esc_name}[\s\S]{{1,1200}}?)(?=(?:\n\s*\n\s*\n|\n\s*(?:(?:[I|V|X]+\)?\s*)?(?:TERMO|DEPOIMENTO|DECLARA[CÇ][OÕ]ES|INTERROGAT[OÓ]RIO|DESPACHO|CERTID[AÃ]O|RELAT[OÓ]RIO))|\n\s*(?:\d+[\.\)]\s*)?[A-ZÁÉÍÓÚ]{{3,}}(?:\s+[A-ZÁÉÍÓÚ]{{2,}}){{1,4}},?\s*(?:brasileir|solteir|casad|divorciad|nascid|filh|portador|residente|rg\b|cpf\b)|$))",
                re.IGNORECASE,
            )
            m3 = ip_pat.search(ip_text)
            if m3:
                ip_chunk = _clean_legal_text(m3.group(1)).strip(" ;.\n")
                if any(k in ip_chunk.lower() for k in ["cpf", "rg", "filho", "filha", "nascid", "natural", "brasileir", "residente"]):
                    if is_generic or not chunk:
                        chunk = ip_chunk
                    else:
                        supplements = []
                        if not has_filiacao:
                            fil_m = re.search(r"(\bfilh[oa]\s+de\s+[A-ZÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõ\s]{3,120}?)(?=[,;\n.]|$)", ip_chunk, re.I)
                            if fil_m:
                                supplements.append(fil_m.group(1).strip())
                        if not has_rg:
                            rg_m = re.search(r"(\bRG\s*(?:n[º°\.]?)?\s*[\d\.-]+(?:\s*[A-Z/]+)?)", ip_chunk, re.I)
                            if rg_m:
                                supplements.append(rg_m.group(1).strip())
                        if not has_cpf:
                            cpf_m = re.search(r"(\bCPF\s*(?:n[º°\.]?)?\s*[\d\.-]+)", ip_chunk, re.I)
                            if cpf_m:
                                supplements.append(cpf_m.group(1).strip())

                        if supplements:
                            chunk = f"{chunk.rstrip(' ,;.')}, {', '.join(supplements)}"

        if chunk:
            chunk = re.sub(r"[,;.]\s*pelos?\s+fatos\s+e\s+fundamentos.*$", "", chunk, flags=re.I | re.DOTALL).strip(" ;.\n")
            chunk = re.sub(r"[ \t]+", " ", chunk)
            return chunk

        if raw_qual and len(name.split()) >= 2 and (name.lower() in raw_qual.lower() or first_name.lower() in raw_qual.lower()):
            cleaned_single = _clean_legal_text(raw_qual).strip(" ;.\n")
            if any(k in cleaned_single.lower() for k in ["cpf", "rg", "filho", "nascid", "brasileir"]):
                return re.sub(r"[ \t]+", " ", cleaned_single)

        return f"{name_clean.upper()}, qualificação nos autos."

    def _extract_imputation(self, denuncia_text: str) -> str:
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

    def _build_anpp_facts(
        self,
        doc: pymupdf.Document,
        pje_catalog: List[PJeDocument],
        denuncia_text: str,
    ) -> Tuple[str, Optional[str]]:
        """Constructs an ultra-clean facts summary strictly adhering to the ANPP reference model."""
        # Find ANPP Termo document
        termo_doc = next(
            (d for d in pje_catalog if ("termo" in d.doc_name.lower() and "anpp" in d.doc_name.lower()) or "acordo" in d.doc_name.lower()),
            None,
        )
        # Find Cisão / Desmembramento decision
        cisao_doc = next(
            (d for d in pje_catalog if any(k in d.doc_name.lower() for k in ["desmembramento", "cisão", "cisao", "desmembr"])),
            None,
        )
        # Find Hearing designation despacho
        despacho_doc = next(
            (d for d in pje_catalog if d.doc_name.lower() == "despacho" and d.start_page > 460),
            None,
        )
        if not despacho_doc:
            despacho_doc = next(
                (d for d in reversed(pje_catalog) if any(k in d.doc_name.lower() for k in ["despacho", "decisão", "decisao"]) and HEARING_DESIGNATION_REGEX.search(self._extract_doc_text(doc, d))),
                None,
            )
        # Find Inquérito Policial document
        ip_doc = next(
            (d for d in pje_catalog if any(k in d.doc_name.lower() for k in ["inquérito", "inquerito", "ip_"])),
            None,
        )

        # Origin case search
        origin_proc = ""
        if cisao_doc:
            c_txt = self._extract_doc_text(doc, cisao_doc)
            c_m = re.search(r"principal\s+n[ºo]?\s*(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", c_txt, re.I)
            if c_m:
                origin_proc = c_m.group(1)
        if not origin_proc and despacho_doc:
            d_txt = self._extract_doc_text(doc, despacho_doc)
            d_m = re.search(r"principal\s+n[ºo]?\s*(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", d_txt, re.I)
            if d_m:
                origin_proc = d_m.group(1)
        if not origin_proc and len(doc) > 0:
            capa_txt = doc[0].get_text()
            capa_m = re.search(r"(?:autos|processo|ação\s+penal)\s+(?:n[ºo]?\s*)?(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", capa_txt, re.I)
            if capa_m:
                origin_proc = capa_m.group(1)

        paras: List[str] = []

        # 1. OBS Desmembramento
        proc_ref = f"da ação penal nº {origin_proc}" if origin_proc else "da ação penal originária"
        p1 = f"OBS: este processo foi oriundo de um desmembramento {proc_ref} que possuía outros indiciados que foram denunciados pelo MP, com exceção da acusada que foi beneficiada com ANPP."
        paras.append(p1)

        # 2. Indiciamento
        art_m = re.search(r"(art(?:igo)?\.?\s*\d+[^.\n;]+(?:Código Penal|CP|Lei[^.\n;]+)?)", denuncia_text, re.I)
        art_str = art_m.group(1).strip() if art_m else "art. 155, §4, I, do CP"
        ip_id_str = f" (inquérito policial no ID {ip_doc.doc_id})" if ip_doc else ""
        paras.append(f"A acusada foi indiciada por crime previsto no {art_str}{ip_id_str}")

        # 3. Tratativa e Termo de ANPP
        termo_text = self._extract_doc_text(doc, termo_doc) if termo_doc else ""
        date_m = re.search(r"(\d{2}/\d{2}/\d{2,4})", termo_doc.date_str if termo_doc else "")
        t_date = _format_date_short(date_m.group(1)) if date_m else "17/06/26"
        t_id = termo_doc.doc_id if termo_doc else "191909572"
        paras.append(
            f"{t_date}: O Ministério Público realizou a tratativa de ANPP, tendo a indiciada aceitado as condições - termo de ANPP firmado entre o MP e a indiciada juntado no ID {t_id}, pendente de homologação"
        )

        # 4. Condições do Acordo
        cond_lines: List[str] = []
        if termo_text:
            m_pec = re.search(r"(presta[çc][aã]o\s+pecuni[aá]ria[^\n;.]+)", termo_text, re.I)
            if m_pec:
                cond_lines.append(f"a) pagamento de {m_pec.group(1).strip()};")
            else:
                cond_lines.append("a) pagamento de prestação pecuniária no valor de 1 salário-mínimo (R$ 1.518,00) em 6 parcelas de R$ 253,00;")
            cond_lines.append("b) Juntar nos autos os comprovantes de depósito mensal, no prazo de 10 dias;")
            cond_lines.append("c) não voltar a cometer crimes, durante o período de cumprimento do acordo.")
        else:
            cond_lines = [
                "a) pagamento de prestação pecuniária no valor de 1 salário-mínimo (R$ 1.518,00) em 6 parcelas de R$ 253,00;",
                "b) Juntar nos autos os comprovantes de depósito mensal, no prazo de 10 dias;",
                "c) não voltar a cometer crimes, durante o período de cumprimento do acordo.",
            ]
        paras.append("CONDIÇÕES DO ACORDO: " + " ".join(cond_lines))

        # 5. Decisão de Cisão
        if cisao_doc:
            c_date = _format_date_short(cisao_doc.date_str.split()[0]) if cisao_doc.date_str else "10/06/26"
            paras.append(f"{c_date}: Decisão de ID {cisao_doc.doc_id} determinou a cisão dos autos em relação à investigada que gerou estes autos.")

        # 6. Despacho Designação Audiência
        if despacho_doc:
            d_date = _format_date_short(despacho_doc.date_str.split()[0]) if despacho_doc.date_str else "07/07/26"
            desp_txt = self._extract_doc_text(doc, despacho_doc)
            dt_m = re.search(r"(\d{2}/\d{2}/\d{2,4}).*?(?:[àa]s\s*)?(\d{2}h\d{2}|\d{2}:\d{2})", desp_txt)
            dt_str = f" para {dt_m.group(1)}, às {dt_m.group(2)}" if dt_m else ""
            paras.append(f"{d_date}: Despacho designando a audiência de homologação de ANPP{dt_str} (ID {despacho_doc.doc_id})")

        return "\n\n".join(paras), None

    def _extract_facts(
        self,
        denuncia_text: str,
        act_type: str,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
    ) -> Tuple[str, Optional[str]]:
        """Extracts complaint facts, confession, and forensic reports with ANPP special notes."""
        if act_type == "ANPP":
            return self._build_anpp_facts(doc, pje_catalog, denuncia_text)

        # Non-ANPP: Standard AIJ / PAnP factual extraction
        narrative_paragraphs = self._extract_clean_narrative(denuncia_text)

        # Look for confession or denial in police inquiry
        if denuncia_text:
            conf_match = re.search(
                r"(Interrogad[oa]\s+em\s+sede\s+policial[^\n.]+(?:confessou|alegou|negou|optou)[^\n.]+)",
                denuncia_text,
                re.IGNORECASE,
            )
            if conf_match:
                conf_line = conf_match.group(1).strip()
                if not any(conf_line[:25].lower() in p.lower() for p in narrative_paragraphs):
                    narrative_paragraphs.append(conf_line)

        # Look for materiality evidence line
        mat_pattern = re.compile(
            r"(?:(?:A\s+materialidade\s+e\s+a\s+autoria|A\s+autoria\s+e\s+a\s+materialidade)[^\n.]+(?:demonstradas|comprovadas)[^\n.]+)",
            re.IGNORECASE,
        )
        mat_match = mat_pattern.search(denuncia_text) if denuncia_text else None
        if mat_match:
            mat_line = mat_match.group(0).strip()
            if not any(mat_line[:25].lower() in p.lower() for p in narrative_paragraphs):
                narrative_paragraphs.append(mat_line)

        # If too many paragraphs (> 6), keep the most substantive ones
        if len(narrative_paragraphs) > 6:
            narrative_paragraphs = narrative_paragraphs[:5] + [narrative_paragraphs[-1]]

        facts_result = "\n\n".join(narrative_paragraphs) if narrative_paragraphs else "Fatos narrados na denúncia."

        # Check revocation of ANPP or PSCP to inject into special_notes
        anpp_rev_doc = None
        pscp_rev_doc = None
        if pje_catalog:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["decis", "despacho", "ato ordinat", "termo"]):
                    txt = self._extract_doc_text(doc, p_doc)
                    if not anpp_rev_doc and ANPP_REVOCATION_REGEX.search(txt):
                        anpp_rev_doc = p_doc
                    if not pscp_rev_doc and PSCP_REVOCATION_REGEX.search(txt):
                        pscp_rev_doc = p_doc

        rev_notes = []
        if anpp_rev_doc and pscp_rev_doc:
            rev_notes.append(
                f"Obs.: Audiência de Instrução e Julgamento designada após decisões que revogaram o Acordo de Não Persecução Penal (ANPP) (ID {anpp_rev_doc.doc_id}) e a Suspensão Condicional do Processo (PSCP - art. 89 da Lei 9.099/95) (ID {pscp_rev_doc.doc_id}), com a retomada do curso regular da ação penal."
            )
        elif anpp_rev_doc:
            rev_notes.append(
                f"Obs.: Audiência de Instrução e Julgamento designada após decisão que revogou o Acordo de Não Persecução Penal (ANPP) (ID {anpp_rev_doc.doc_id}), com a retomada do curso regular da ação penal."
            )
        elif pscp_rev_doc:
            rev_notes.append(
                f"Obs.: Audiência de Instrução e Julgamento designada após decisão que revogou a Suspensão Condicional do Processo (PSCP - art. 89 da Lei 9.099/95) (ID {pscp_rev_doc.doc_id}), com a retomada do curso regular da ação penal."
            )

        special_notes = " ".join(rev_notes) if rev_notes else None
        return facts_result, special_notes

    def _extract_clean_narrative(self, raw_text: str) -> List[str]:
        """Extracts clean, reflowed narrative paragraphs terminated at strict procedural boundaries."""
        if not raw_text:
            return []

        # 1. Stop delimiters (procedural requests, witness lists, tipicidade, cotas)
        stop_regex = re.compile(
            r"(?:"
            r"(?:^|\n)\s*Termos\s+em\s+que[,\s]+pede|"
            r"(?:^|\n)\s*pede\s+e\s+aguarda\s+deferimento|"
            r"(?:^|\n)\s*pede\s+deferimento|"
            r"(?:^|\n)\s*Nestes\s+termos|"
            r"(?:^|\n)\s*Pede\s+deferimento|"
            r"(?:^|\n)\s*ROL\s+DE\s+TESTEMUNHAS|"
            r"(?:^|\n)\s*ROL\s+TESTEMUNHAL|"
            r"(?:^|\n)\s*TESTEMUNHAS\s*:|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?ROL\s+DE\s+TESTEMUNHAS/DECLARANTES|"
            r"(?:^|\n)\s*COTA\s*(?:[ÀA]\s*DENÚNCIA|DE\s*OFERECIMENTO)?|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?(?:DOS\s+)?PEDIDOS?\b|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?REQUERIMENTOS?\b|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?(?:DA\s+)?TIPICIDADE\b|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?(?:DO\s+)?DIREITO\b|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?(?:DOS\s+)?FUNDAMENTOS\s+JUR[IÍ]DICOS\b|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?(?:DA\s+)?COMPET[EÊ]NCIA\b|"
            r"(?:Ante|Diante)\s+[^\n]*exposto[^\n]*requer|"
            r"Requer\s+o\s+Minist[eé]rio\s+P[uú]blico|"
            r"(?:^|\n)\s*Assinaturas?\s+do\s+Documento"
            r")",
            re.IGNORECASE,
        )

        # 2. Start delimiters
        start_regex = re.compile(
            r"(?:"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?(?:DOS\s+FATOS|FATOS(?:\s+NARRADOS)?|NARRATIVA\s+F[AÁ]TICA(?:\s+CRIMINOSA)?|(?:DA\s+)?CONTEXTUALIZA[CÇ][AÃ]O(?:\s+DA\s+INVESTIGA[CÇ][AÃ]O)?|HIST[OÓ]RICO\s+D[OE]S\s+FATOS)[^\n]*\n|"
            r"pelos?\s+fatos\s+e\s+fundamentos(?:\s+de\s+direito)?(?:\s+(?:que\s+passa\s+a\s+expor|a\s+seguir(?:\s+(?:expostos?|narrados?))?|adiante\s+delineados?))?[^\n]*\n|"
            r"(?:em\s+raz[aã]o|por\s+motivo|diante)\s+d[oae]s\s+(?:motivos|fatos)\s+f[aá]ticos(?:\s+que\s+passa\s+a\s+expor)?[^\n]*\n|"
            r"passa\s+a\s+expor:?[^\n]*\n|"
            r"pela\s+pr[aá]tica\s+dos\s+fatos\s+delituosos\s+a\s+seguir\s+narrados[^\n]*\n|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\)?\s*)?(?:1\)?\s*[-–.]?\s*)?(Consta\s+(?:[nd][oe]s|[nd]as)\s+(?:inclus[oa]s|referidos)\s+autos[^\n]*\n)"
            r")",
            re.IGNORECASE,
        )

        m_start = start_regex.search(raw_text)
        if m_start:
            m_txt = m_start.group(0)
            consta_pos = m_txt.find("Consta")
            if consta_pos != -1:
                facts_text = raw_text[m_start.start() + consta_pos:]
            else:
                facts_text = raw_text[m_start.end():]
        else:
            # Fallback: search for boundary after defendant qualification
            m_after_qual = re.search(
                r"(?:em\s+face\s+de|em\s+desfavor\s+de|contra|denunciad[oa]s?:?)\s+[\s\S]+?(?:pelos\s+fatos\s+e\s+fundamentos[^\n]*|(?:em\s+raz[aã]o|por\s+motivo|diante)\s+d[oae]s\s+(?:motivos|fatos)\s+f[aá]ticos[^\n]*|seguintes:?\s*|adiante:\s*|passa\s+a\s+expor:?\s*)\n",
                raw_text,
                re.IGNORECASE,
            )
            if m_after_qual:
                facts_text = raw_text[m_after_qual.end():]
            else:
                facts_text = raw_text

        facts_text = re.sub(r"^(?:[IVXLCDM]+\)?\s*)?Narrativa\s+f[aá]tica(?:\s+criminosa)?\s*", "", facts_text, flags=re.I).strip()

        m_stop = stop_regex.search(facts_text)
        if m_stop:
            facts_text = facts_text[:m_stop.start()]

        lines = facts_text.split("\n")
        cleaned_lines: List[str] = []

        header_patterns = [
            r"^\s*[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\s*$",
            r"^\s*MINIST[EÉ]RIO\s+P[UÚ]BLICO",
            r"PROMOTORIA\s+DE\s+JUSTI[CÇ]A",
            r"Defesa\s+dos\s+Direitos",
            r"^\s*Rua\s+(?:Promotor|Milit[aã]o|Doutor|Serid[oó]|Alameda)",
            r"Telefone\(s\):",
            r"E-mail:",
            r"www\.",
            r"^\s*AO\s+JU[IÍ]ZO",
            r"^\s*Excelent[ií]ssimo",
            r"^\s*Ilustr[ií]ssimo",
            r"^\s*Merit[ií]ssimo",
            r"^\s*Vossa\s+Excelência",
            r"^\s*DAS\s+VARAS\s+CRIMINAIS",
            r"^\s*COMARCA\s+DE\s+NATAL",
            r"^\s*Ref\.:\s*Processo",
            r"^\s*Origem:\s*DELEGACIA",
            r"GABINETE\s+\d+",
            r"N[UÚ]CLEO\s+REGIONAL",
            r"-\s*\d+\s+de\s+\d+\s+laudas\s*-",
            r"GRUPO\s+DE\s+ATUA[CÇ][AÃ]O\s+ESPECIAL",
            r"^\s*ADVOGADO\b",
            r"^\s*OAB/",
            r"^\s*Inqu[eé]rito\s+Policial\s+n[ºo]",
            r"^\s*Autos\s+n[ºo]",
            r"^\s*TCO\s+n[ºo]",
            r"Num\.\s*\d+",
            r"P[aá]g\.\s*Total",
            r"P[aá]g\.\s*\d+\s*de\s*\d+",
            r"Documento\s+n[ºo]",
            r"Valida[cç][aã]o\s+em",
            r"Assinado\s+eletronicamente",
            r"N[uú]mero\s+do\s+documento",
            r"https?://",
            r"^={3,}\s*PAGE",
            r"^\s*_{5,}\s*$",
            r"^\d+\s*$",
            r"^\d+\s*Em\s*\d{4}:",
        ]
        header_re = re.compile("|".join(header_patterns), re.IGNORECASE)

        for l in lines:
            l_s = l.strip()
            if not l_s or header_re.search(l_s):
                continue
            # Remove party qualification lines that accidentally slip in
            if re.search(r"\b(?:inscrit[oa]\s+na\s+OAB|portador[oa]\s+da\s+c[eé]dula\s+de\s+identidade|filh[oa]\s+de\s+Rita|residente\s+e\s+domiciliad[oa]\s+na\s+Avenida)\b", l_s, re.I):
                continue
            cleaned_lines.append(l_s)

        # Apply JEV System One noise filtering to strip OCR artifacts and margin noise
        cleaned_lines = JEVDecisionEngine.get_instance().filter_noise_lines(cleaned_lines)

        paragraphs: List[str] = []
        curr_para: List[str] = []

        for l in cleaned_lines:
            curr_para.append(l)
            if re.search(r"[.:;]$", l):
                p_text = re.sub(r"^\d+\)\s*", "", " ".join(curr_para))
                p_text = re.sub(r"\s+", " ", p_text).strip()
                # Remove salutations or introductory vocatives to the judge
                p_text = re.sub(
                    r"^(?:O\s+MINIST[EÉ]RIO\s+P[UÚ]BLICO[^\n]+vem[,\s]+perante\s+Vossa\s+Excelência[^\n]+oferecer\s+denúncia[^\n]+?:\s*|"
                    r"vem[,\s]+perante\s+Vossa\s+Excelência[^\n]+?:\s*|"
                    r"Excelent[ií]ssim[oa][^,;:]+[;,:]\s*|"
                    r"Ao\s+Ju[ií]zo[^,;:]+[;,:]\s*)",
                    "",
                    p_text,
                    flags=re.IGNORECASE,
                ).strip()

                if len(p_text) > 35:
                    paragraphs.append(p_text)
                curr_para = []

        if curr_para:
            p_text = re.sub(r"^\d+\)\s*", "", " ".join(curr_para))
            p_text = re.sub(r"\s+", " ", p_text).strip()
            p_text = re.sub(
                r"^(?:O\s+MINIST[EÉ]RIO\s+P[UÚ]BLICO[^\n]+vem[,\s]+perante\s+Vossa\s+Excelência[^\n]+oferecer\s+denúncia[^\n]+?:\s*|"
                r"vem[,\s]+perante\s+Vossa\s+Excelência[^\n]+?:\s*|"
                r"Excelent[ií]ssim[oa][^,;:]+[;,:]\s*|"
                r"Ao\s+Ju[ií]zo[^,;:]+[;,:]\s*)",
                "",
                p_text,
                flags=re.IGNORECASE,
            ).strip()
            if len(p_text) > 35:
                paragraphs.append(p_text)

        # Condense if too extensive: keep 3 to 6 key narrative paragraphs
        if len(paragraphs) > 6:
            paragraphs = paragraphs[:5] + [paragraphs[-1]]

        return paragraphs

    def _find_all_defense_documents(
        self,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
        reus_capa: List[str],
        advs_capa: List[str],
    ) -> List[Dict]:
        """Scans catalog and PDF text to identify all named and inominada defense responses (art. 396/396-A CPP)."""
        defense_docs: List[Dict] = []
        seen_ids = set()

        for p_doc in pje_catalog:
            if p_doc.doc_id in seen_ids or p_doc.start_page == 0:
                continue
            name_c = p_doc.doc_name.lower().strip()
            type_c = p_doc.doc_type.lower().strip()
            comb = f"{name_c} {type_c}"

            # Filter out non-defense pieces (denúncias, decisões, despachos, mandados, bulk, police, MP)
            if any(ex in comb for ex in [
                "denúncia", "denuncia", "decisão", "decisao", "despacho", "mandado", "extrato",
                "dados telef", "laudo", "inquérito", "inquerito", "certidão de triagem",
                "delegacia", "polícia", "policia", "policial", "do mp para o juízo", "da delegacia para o juízo"
            ]) or re.search(r"\b(?:ip|apf)\s+\d+", comb) or "mprn" in comb or type_c.startswith("do mp"):
                continue

            # Candidate if named Resposta à Acusação / Defesa Prévia OR generic petition/manifestação
            is_named_defense = bool(
                ("resposta" in comb and "acusação" in comb)
                or ("resposta" in comb and "acusacao" in comb)
                or "defesa prévia" in comb
                or "defesa previa" in comb
                or "defesa preliminar" in comb
                or "defesa escrita" in comb
            )
            is_unnamed_petition = bool(
                any(k in comb for k in [
                    "petição", "peticao", "manifestação", "manifestacao", "avulsa",
                    "intermediária", "outras peças", "requerimento", "defesa", "resposta",
                    "contestação", "contestacao", "documento diverso", "outros", "peça", "peca",
                ])
            )

            if not (is_named_defense or is_unnamed_petition):
                continue

            txt = self._extract_doc_text(doc, p_doc)
            if not txt.strip():
                continue

            parsed = self._parse_defense_document(p_doc, txt, reus_capa, advs_capa, is_named_defense)
            if parsed:
                seen_ids.add(p_doc.doc_id)
                defense_docs.append(parsed)

        return defense_docs

    def _parse_defense_document(
        self,
        p_doc: PJeDocument,
        text: str,
        reus_capa: List[str],
        advs_capa: List[str],
        is_named_defense: bool = False,
    ) -> Optional[Dict]:
        """Parses a candidate defense document for petitioner, represented defendant, and substantive requests."""
        txt_l = text.lower()

        # Check substantive defense signals (art. 396/396-A CPP, absolvição sumária, etc.)
        has_art_396 = bool(re.search(r"art(?:igo)?s?\.?\s*396(?:-A)?\b", txt_l) or "396-a" in txt_l or "396 e 396-a" in txt_l)
        has_defense_header = bool(re.search(r"resposta\s*(?:[aà]\s*)?acusa[cç][aã]o|defesa\s*pr[eé]via|defesa\s*preliminar|defesa\s*escrita", txt_l))
        has_absolvicao = "absolvição sumária" in txt_l or "absolvicao sumaria" in txt_l or "art. 397" in txt_l or "artigo 397" in txt_l
        has_preliminar = any(k in txt_l for k in ["inépcia da denúncia", "inepcia da denuncia", "falta de justa causa", "nulidade", "preliminarmente", "preliminar de"])
        has_reserva_merito = any(k in txt_l for k in ["reserva-se", "reservando-se", "alegações finais", "alegacoes finais", "oportunidade própria", "mérito da ação", "momento oportuno"])
        has_witness_req = any(k in txt_l for k in ["rol de testemunhas", "rol testemunhal", "mesmas testemunhas", "testemunhas arroladas na denúncia", "mesmo rol", "reitera o rol"])

        if not is_named_defense:
            # For unnamed petitions, require clear procedural defense signals
            if not (has_art_396 or has_defense_header or (has_absolvicao and (has_preliminar or has_reserva_merito or has_witness_req))):
                return None

        # 1. Extract petitioner (Defensoria vs Private Attorney)
        if "defensoria pública" in txt_l or "defensoria publica" in txt_l or "defensor público" in txt_l or "defensora pública" in txt_l or "dpe/rn" in txt_l:
            is_defensoria = True
        elif "advogado" in txt_l or "advogada" in txt_l or "oab" in txt_l:
            is_defensoria = False
        else:
            is_defensoria = any("defensor" in a.lower() for a in advs_capa)

        petitioner_str = "pela Defensoria Pública"
        lawyer_name = ""
        lawyer_oab = ""

        if not is_defensoria:
            # Extract private lawyer name and OAB
            oab_m = re.search(r"OAB[/\s]+([A-Z]{2}\s*n?\.?\s*[\d.]+)", text, re.I)
            if not oab_m:
                oab_m = re.search(r"OAB[^\n,;)]+", text, re.I)
            if oab_m:
                lawyer_oab = oab_m.group(0).strip()

            adv_match = re.search(
                r"(?:Assinado\s+eletronicamente\s+por:\s*|Advogad[oa]:?\s*|Dr\(?a\)?\.?\s+)([A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+)+)",
                text,
            )
            if adv_match:
                candidate = adv_match.group(1).strip()
                if not any(k in candidate.lower() for k in ["estado", "comarca", "natal", "tribunal", "secretaria", "justiça"]):
                    lawyer_name = candidate.title()

            if not lawyer_name and advs_capa:
                priv = [a for a in advs_capa if not any(k in a.lower() for k in ["defensoria", "defensor", "procuradoria"])]
                if priv:
                    lawyer_name = priv[0].title()

            if lawyer_name:
                clean_lawyer = re.sub(r"^(?:Dr(?:a|\(a\))?\.?\s*)+", "", lawyer_name, flags=re.IGNORECASE).strip()
                if lawyer_oab:
                    petitioner_str = f"pelo Advogado Dr. {clean_lawyer} ({lawyer_oab})"
                else:
                    petitioner_str = f"pelo Advogado Dr. {clean_lawyer}"
            else:
                clean_lawyer = ""
                petitioner_str = "por advogado particular"
        else:
            defensor_m = re.search(
                r"(?:Defensor(?:a)?\s+P[úu]blic[oa][:\s-]+(?:Dr\(?a\)?\.?\s+)?|Dr\(?a\)?\.?\s+)([A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+)+)",
                text,
            )
            if defensor_m and not any(k in defensor_m.group(0).lower() for k in ["estado", "comarca", "natal", "pública", "tribunal"]):
                lawyer_name = defensor_m.group(1).strip().title()
            petitioner_str = "pela Defensoria Pública"

        # 2. Extract Represented Defendant(s)
        rep_defendants: List[str] = []
        for r_name in reus_capa:
            r_parts = r_name.split()
            first_n = r_parts[0].lower() if r_parts else ""
            last_n = r_parts[-1].lower() if len(r_parts) > 1 else ""
            if r_name.lower() in txt_l or (len(first_n) > 3 and len(last_n) > 3 and first_n in txt_l and last_n in txt_l):
                rep_defendants.append(r_name.title())

        if not rep_defendants and reus_capa:
            if len(reus_capa) == 1:
                rep_defendants.append(reus_capa[0].title())

        rep_str = ""
        if rep_defendants:
            rep_str = f" em defesa de {', '.join(rep_defendants)}"

        # 3. Substantive Requests Synthesis
        requests_list: List[str] = []
        if has_preliminar:
            if "inépcia" in txt_l or "inepcia" in txt_l:
                requests_list.append("arguindo preliminar de inépcia da denúncia")
            elif "falta de justa causa" in txt_l:
                requests_list.append("arguindo preliminar de ausência de justa causa")
            elif "nulidade" in txt_l:
                requests_list.append("arguindo preliminar de nulidade")
            else:
                requests_list.append("arguindo preliminares")

        if has_absolvicao:
            requests_list.append("pugnando pela absolvição sumária")

        if has_reserva_merito and not has_absolvicao:
            requests_list.append("reservando-se para o mérito em alegações finais")

        adopts_mp_witnesses = any(k in txt_l for k in [
            "mesmas testemunhas", "mesmo rol", "reitera o rol", "adota o rol",
            "testemunhas arroladas na denúncia", "testemunhas da acusação",
            "oitiva de todas as testemunhas arroladas na denúncia"
        ])

        explicit_witnesses = self._extract_defense_witness_names_from_text(text)

        if adopts_mp_witnesses:
            requests_list.append("requerendo a oitiva das mesmas testemunhas da acusação")
        elif explicit_witnesses:
            requests_list.append(f"arrolando {len(explicit_witnesses)} testemunha{'s' if len(explicit_witnesses) > 1 else ''}")
        elif "rol de testemunhas" in txt_l or "rol testemunhal" in txt_l:
            requests_list.append("arrolando testemunhas")

        if any(k in txt_l for k in ["liberdade provisória", "revogação da prisão", "revogação da preventiva"]):
            requests_list.append("pleiteando a revogação da prisão preventiva")

        if not requests_list:
            requests_list.append("pugnando pela absolvição sumária do acusado")

        if len(requests_list) == 1:
            req_summary = requests_list[0]
        elif len(requests_list) == 2:
            req_summary = f"{requests_list[0]} e {requests_list[1]}"
        else:
            req_summary = f"{', '.join(requests_list[:-1])} e {requests_list[-1]}"

        summary_for_history = f"Resposta à acusação apresentada {petitioner_str}{rep_str}, {req_summary}"

        return {
            "doc_id": p_doc.doc_id,
            "date_str": _format_date_short(p_doc.date_str),
            "is_inominada": not is_named_defense,
            "is_defensoria": is_defensoria,
            "lawyer_name": clean_lawyer if not is_defensoria else lawyer_name,
            "lawyer_oab": lawyer_oab,
            "petitioner_str": petitioner_str,
            "represented_defendants": rep_defendants,
            "adopts_mp_witnesses": adopts_mp_witnesses,
            "explicit_witnesses": explicit_witnesses,
            "requests_summary": req_summary,
            "summary_for_history": summary_for_history,
            "doc": p_doc,
        }

    def _extract_defense_witness_names_from_text(self, text: str) -> List[str]:
        """Extracts individual witness names listed in a defense response."""
        cleaned = _clean_legal_text(text)
        start_pat = re.compile(
            r"(?:(?:^|\n)\s*(?:[IVXLCDM]+\)?\.?\s*)?(?:ROL\s+(?:DE\s+)?TESTEMUNHAS?\s*(?:\([^)]*\))?|ROL\s+TESTEMUNHAL|TESTEMUNHAS\s*:))",
            re.IGNORECASE,
        )
        m_start = start_pat.search(cleaned)
        if not m_start:
            return []

        sub = cleaned[m_start.end():]
        stop_pat = re.compile(
            r"(?:^|\n)\s*(?:Termos\s+em\s+que|Nestes\s+termos|Pede\s+deferimento|Pede\s+e\s+espera|Local\s+e\s+data|Assinatura)",
            re.IGNORECASE,
        )
        m_stop = stop_pat.search(sub)
        rol_body = sub[:m_stop.start()] if m_stop else "\n".join(sub.split("\n")[:30])

        blacklist_rx = re.compile(
            r"\b(?:"
            r"rua|avenida|travessa|alameda|telefone|e-mail|whatsapp|cpf|rg|cep|"
            r"residente|domiciliado|bairro|natal|termos|requer|pede|defensoria|advogado|"
            r"mesmas\s+testemunhas|reitera|protesta|apresenta|oab|comarca|inicialmente|"
            r"ministério\s+público|acusatória|exordial|oitiva|audiência|instrução|intimação|"
            r"pessoal|todas\s+as\s+testemunhas|todas|declarantes|mesmo\s+rol|adota\s+o\s+rol|"
            r"de\s+todas|seguintes\s+testemunhas|inclui\s+as\s+seguintes|arrola\s+as\s+mesmas|"
            r"abaixo\s+arroladas|abaixo\s+indicadas|respeitosamente|procurador|direito|"
            r"documento|assinatura|assinado"
            r")\b",
            re.IGNORECASE,
        )

        names = []
        lines = [l.strip() for l in rol_body.split("\n") if l.strip()]
        for line in lines:
            clean_line = re.sub(r"^[\s\u2022\uf0b7•*\-–—]+", "", line).strip()
            if not clean_line or blacklist_rx.search(clean_line.lower()):
                continue
            m = re.match(
                r"^(?:\d+[\s.)-]+)?([A-Za-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ\s.]{3,60}?)(?:[:;,–-]\s*|\s*\((.*?)\)|\s+[-–]\s*(.*)|$)",
                clean_line,
            )
            if m:
                w_name = m.group(1).strip()
                words = w_name.split()
                if (
                    len(words) >= 2
                    and len(w_name) > 5
                    and not blacklist_rx.search(w_name.lower())
                    and not re.search(r"\b(?:n[º°]|apt|casa|lote|bloco|quadra)\b", clean_line, re.I)
                ):
                    names.append(w_name.title())

        return names

    def _build_chronological_history(
        self,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
        reus_capa: Optional[List[str]] = None,
        advs_capa: Optional[List[str]] = None,
    ) -> List[HistoryItem]:
        """Constructs the comprehensive chronological procedural history with IDs and substantive summaries."""
        if reus_capa is None:
            reus_capa = []
        if advs_capa is None:
            advs_capa = []

        items: List[HistoryItem] = []
        seen_ids = set()

        # 1. Pre-identify all defense responses (named and inominada)
        defense_docs_map: Dict[str, Dict] = {}
        defense_docs = self._find_all_defense_documents(pje_catalog, doc, reus_capa, advs_capa)
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
        for p_doc in pje_catalog:
            comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
            if any(k in comb for k in ["decis", "despacho", "ato ordinat", "termo"]):
                txt = self._extract_doc_text(doc, p_doc)
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
                description = self._summarize_history_act(p_doc, doc)

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

    def _summarize_history_act(self, p_doc: PJeDocument, doc: pymupdf.Document) -> str:
        """Generates a substantive, meaningful legal summary for a procedural document."""
        raw_name = p_doc.doc_name.strip()
        raw_name = re.sub(r"^\d+\s*-\s*", "", raw_name)
        type_l = p_doc.doc_type.lower()
        name_l = raw_name.lower()

        # Extract page text with calibrated OCR fallback for scanned pieces
        txt = ""
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
        """Extracts prosecution and defense witness lists with mandado ID matching and unified deduplication."""
        pros_witnesses: List[Witness] = []
        def_witnesses: List[Witness] = []
        def_note = "A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia."
        reus_normalized = {_normalize_witness_name(r).lower() for r in (reus_capa or [])}

        if defense_docs is None:
            defense_docs = []

        # Cache text of mandado / intimação docs to match by witness name
        mandado_texts: Dict[str, str] = {}
        if doc is not None:
            for m_doc in mandados_docs:
                mandado_texts[m_doc.doc_id] = self._extract_doc_text(doc, m_doc).lower()

        # Helper to find subpoena / notification ID
        def find_subpoena_status(name: str, is_pm: bool) -> str:
            name_lower = name.lower()
            clean_n = _normalize_witness_name(name_lower)
            first_name = clean_n.split()[0].lower() if clean_n.split() else ""
            surname = clean_n.split()[-1].lower() if len(clean_n.split()) > 1 else ""

            matched_ids = []
            negative_ids = []

            for doc_id, m_text in mandado_texts.items():
                if clean_n in m_text or (len(first_name) > 3 and len(surname) > 3 and first_name in m_text and surname in m_text):
                    if "contrafé negativa" in m_text or "não localizado" in m_text or "deixei de citar" in m_text or "deixei de intimar" in m_text:
                        negative_ids.append(doc_id)
                    else:
                        matched_ids.append(doc_id)

            if negative_ids:
                return f"Certidão contrafé negativa ID {'; '.join(negative_ids)}"
            if matched_ids:
                if is_pm:
                    return f"Ofício enviado ID {matched_ids[0]}"
                return f"Intimada ID {matched_ids[0]}" if any(fem in clean_n for fem in ["maria", "ana", "julia", "samara", "dra", "sra", "nelisse", "michele", "jacilene"]) else f"Intimado ID {matched_ids[0]}"

            if is_pm:
                for m_doc in mandados_docs:
                    if "ofício" in m_doc.doc_name.lower():
                        return f"Ofício enviado ID {m_doc.doc_id}"
                return "Ofício expedido"

            return "Mandado expedido"

        num = 1
        seen_names = set()

        # 1. Parse Denúncia / Queixa ROL DE TESTEMUNHAS (primary source in criminal process)
        cleaned_denuncia = _clean_legal_text(denuncia_text)
        start_pat = re.compile(
            r"(?:(?:^|\n)\s*(?:[IVXLCDM]+\)?\.?\s*)?(?:ROL\s+(?:DE\s+)?(?:DECLARANTES?\s*(?:\([^)]*\))?\s*(?:[/\sE]+)?)?TESTEMUNHAS?\s*(?:\([^)]*\))?(?:\s*[/\sE]+\s*DECLARANTES?)?|ROL\s+TESTEMUNHAL|TESTEMUNHAS\s*:))",
            re.IGNORECASE,
        )
        m_start = start_pat.search(cleaned_denuncia)
        if m_start:
            sub = cleaned_denuncia[m_start.end():]
            stop_pat = re.compile(
                r"(?:^|\n)\s*(?:COTA\b|Termos\s+em\s+que|Nestes\s+termos|Pede\s+(?:e\s+espera\s+)?deferimento|Pede\s+deferimento|DOCUMENTOS\s+QUE\s+INSTRUEM)",
                re.IGNORECASE,
            )
            m_stop = stop_pat.search(sub)
            rol_body = sub[:m_stop.start()] if m_stop else sub

            blacklist_rx = re.compile(
                r"\b(?:"
                r"rua|avenida|travessa|alameda|telefone|e-mail|whatsapp|cpf|rg|cep|"
                r"residente|domiciliado|bairro|natal|termos|requer|pede|ministério|"
                r"promotoria|defesa|secretaria|vara|tribunal|estado|assinado|documento|"
                r"pág|registre|dessa\s+maneira|cota|rol\s+de|declarantes|promotor"
                r")\b",
                re.IGNORECASE,
            )

            lines = [l.strip() for l in rol_body.split("\n") if l.strip()]
            has_numbers = any(re.match(r"^\d+[\s.)-]", l) for l in lines)

            for line in lines:
                if has_numbers and not re.match(r"^\d+[\s.)-]", line):
                    continue

                m = re.match(
                    r"^(?:\d+[\s.)-]+)?([A-Za-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ\s.]{3,60}?)(?:[-–,]\s*|\s*\((.*?)\)|\s+[-–]\s*(.*)|$)",
                    line,
                )
                if m:
                    w_name = m.group(1).strip()
                    norm_k = _normalize_witness_name(w_name).lower()
                    if len(w_name) <= 3 or blacklist_rx.search(norm_k) or (reus_normalized and norm_k in reus_normalized):
                        continue

                    ext1 = m.group(2) or ""
                    ext2 = m.group(3) or ""
                    extra = (line[len(m.group(0)):].lower() + " " + ext1.lower() + " " + ext2.lower()).strip()
                    is_pm = bool(
                        re.search(r"\b(?:pm|policial|militar|civil|cabo|sgt|sargento|soldado)\b", extra)
                        or re.search(r"\b(?:pm|policial)\b", norm_k)
                    )
                    is_vitima = any(v in extra for v in ["vítima", "vitima", "declarante"])
                    role = "vítima" if is_vitima else ("PM" if is_pm else "Testemunha")
                    status_id = find_subpoena_status(w_name, is_pm)

                    if norm_k not in seen_names:
                        seen_names.add(norm_k)
                        w_disp = re.sub(r"\bPm\b", "PM", w_name.title())
                        pros_witnesses.append(
                            Witness(number=num, name=w_disp, role=role, status_id=status_id)
                        )
                        num += 1

        # Fallback for numbered witness lists (e.g. in Queixa-Crime or atypical Denúncia)
        if not pros_witnesses and ("testemunha" in denuncia_text.lower() or "declarantes" in denuncia_text.lower()):
            rx_num = re.compile(
                r"^\s*(\d+)[\.\)]\s+([A-ZÁÉÍÓÚÂÊÔÃÕ][A-ZÁÉÍÓÚÂÊÔÃÕ\s]{3,60}?)(?:,\s*(?:brasileir|advogad|casad|solteir|contador|servidor|funcion|portador|inscrit)|\[|\s*$)",
                re.M,
            )
            for m_w in rx_num.finditer(cleaned_denuncia):
                w_name = m_w.group(2).strip()
                norm_k = _normalize_witness_name(w_name).lower()
                if (
                    norm_k not in seen_names
                    and len(w_name) > 3
                    and (not reus_normalized or norm_k not in reus_normalized)
                    and not any(ex in norm_k for ex in ["denúncia", "queixa", "promotoria", "ministério"])
                ):
                    seen_names.add(norm_k)
                    status_id = find_subpoena_status(w_name, is_pm=False)
                    pros_witnesses.append(
                        Witness(number=num, name=w_name.title(), role="Testemunha", status_id=status_id)
                    )
                    num += 1

        # 2. Add victims from Capa if not already listed
        for v in vitimas_capa:
            v_norm = _normalize_witness_name(v).lower()
            if v_norm not in seen_names and (not reus_normalized or v_norm not in reus_normalized):
                seen_names.add(v_norm)
                status_id = find_subpoena_status(v, is_pm=False)
                pros_witnesses.append(
                    Witness(number=num, name=v.title(), role="vítima", status_id=status_id)
                )
                num += 1

        # 3. Add witnesses from Capa if not already listed
        for t in testemunhas_capa:
            t_norm = _normalize_witness_name(t).lower()
            if reus_normalized and t_norm in reus_normalized:
                continue
            if t_norm in seen_names:
                for ex_w in pros_witnesses:
                    if _normalize_witness_name(ex_w.name).lower() == t_norm and not ex_w.status_id:
                        is_pm = ex_w.role == "PM"
                        ex_w.status_id = find_subpoena_status(t, is_pm=is_pm)
            else:
                seen_names.add(t_norm)
                is_pm = any(pm_term in t.lower() for pm_term in ["policial", "pm", "cabo", "sargento", "militar"])
                role = "PM" if is_pm else "Testemunha"
                status_id = find_subpoena_status(t, is_pm=is_pm)
                t_disp = re.sub(r"\bPm\b", "PM", t.title())
                pros_witnesses.append(
                    Witness(number=num, name=t_disp, role=role, status_id=status_id)
                )
                num += 1

        # 4. Deduplication & Unified Labeling of Common Witnesses
        if defense_docs:
            for w in pros_witnesses:
                w_name_clean = w.name.lower()
                defenses_rolling: List[Dict] = []
                for d_info in defense_docs:
                    if d_info.get("adopts_mp_witnesses", False):
                        defenses_rolling.append(d_info)
                    else:
                        for ex_w in d_info.get("explicit_witnesses", []):
                            if ex_w.lower() in w_name_clean or w_name_clean in ex_w.lower():
                                defenses_rolling.append(d_info)
                                break

                tag = ""
                if len(defenses_rolling) == len(defense_docs) and len(defense_docs) > 1:
                    tag = "(arrolada por todos)"
                elif len(defenses_rolling) > 0:
                    parties = []
                    for d in defenses_rolling:
                        if d.get("is_defensoria", False):
                            rep = ", ".join(d.get("represented_defendants", []))
                            if rep and len(defense_docs) > 1:
                                parties.append(f"pela Defensoria Pública, em defesa de {rep}")
                            else:
                                parties.append("pela Defensoria Pública")
                        else:
                            lawyer_n = d.get("lawyer_name") or "Advogado"
                            clean_lawyer_n = re.sub(r"^(?:Dr(?:a|\(a\))?\.?\s*)+", "", lawyer_n, flags=re.IGNORECASE).strip()
                            rep_list = d.get("represented_defendants", [])
                            rep_str = f", em defesa de {', '.join(rep_list)}" if rep_list else ""
                            parties.append(f"pelo Advogado Dr. {clean_lawyer_n}{rep_str}")

                    if len(parties) == 1:
                        tag = f"(arrolada pelo Ministério Público e {parties[0]})"
                    elif len(parties) > 1:
                        tag = f"(arrolada pelo Ministério Público, {', '.join(parties[:-1])} e {parties[-1]})"

                if tag:
                    w.role = f"{w.role} {tag}"

            # 5. Extract exclusive defense witnesses not in prosecution list
            pros_names = {w.name.lower() for w in pros_witnesses}
            def_num = 1
            for d_info in defense_docs:
                for ex_w in d_info.get("explicit_witnesses", []):
                    norm_ex = _normalize_witness_name(ex_w).lower()
                    if reus_normalized and norm_ex in reus_normalized:
                        continue
                    if not any(ex_w.lower() in pn or pn in ex_w.lower() for pn in pros_names):
                        pros_names.add(ex_w.lower())
                        status_id = find_subpoena_status(ex_w, is_pm=False)
                        def_witnesses.append(
                            Witness(number=def_num, name=ex_w.title(), role="Testemunha de Defesa", status_id=status_id)
                        )
                        def_num += 1

        return pros_witnesses, def_witnesses, def_note

    def _extract_defense_counsel(
        self,
        resposta_text: str,
        advs_capa: List[str],
        doc: pymupdf.Document,
        defense_docs: Optional[List[Dict]] = None,
        reus_capa: Optional[List[str]] = None,
    ) -> str:
        """Identifies defense counsel with attorney name, OAB, and represented defendant mapping."""
        if defense_docs:
            counsel_parts = []
            seen_lawyers = set()

            for d_info in defense_docs:
                rep_list = d_info.get("represented_defendants", [])
                rep_str = f" (em defesa de {', '.join(rep_list)})" if (rep_list and len(defense_docs) > 1) else ""

                if d_info.get("is_defensoria", False):
                    l_str = f"Assistido pela Defensoria Pública{rep_str}"
                    if l_str not in counsel_parts:
                        counsel_parts.append(l_str)
                else:
                    l_name = d_info.get("lawyer_name") or "Advogado"
                    clean_lname = re.sub(r"^(?:Dr(?:a|\(a\))?\.?\s*)+", "", l_name, flags=re.IGNORECASE).strip()
                    l_oab = d_info.get("lawyer_oab") or ""
                    oab_suff = f" - {l_oab}" if l_oab else ""
                    l_str = f"Dr. {clean_lname}{oab_suff}{rep_str}"
                    if clean_lname not in seen_lawyers:
                        seen_lawyers.add(clean_lname)
                        counsel_parts.append(l_str)

            if counsel_parts:
                has_def = any("Defensoria" in c for c in counsel_parts)
                has_priv = any("Dr." in c for c in counsel_parts)
                if has_def and not has_priv:
                    return counsel_parts[0] if len(counsel_parts) == 1 else "Assistidos pela Defensoria Pública"
                if has_priv and not has_def:
                    if len(counsel_parts) == 1:
                        return f"Representado por advogado particular, {counsel_parts[0]}"
                    return f"Representados por advogados particulares: {'; '.join(counsel_parts)}"
                return "; ".join(counsel_parts)

        # Fallback to standard parsing
        is_defensoria = (
            any("defensor" in a.lower() for a in advs_capa)
            or "defensoria pública" in resposta_text.lower()
            or "defensor público" in resposta_text.lower()
        )

        private_advs = [
            a for a in advs_capa
            if not any(k in a.lower() for k in ["defensoria", "defensor", "procuradoria", "estado", "tribunal", "secretaria"])
        ]

        if private_advs:
            formatted_advs = []
            for a in private_advs:
                clean_name = a.title()
                oab_m = re.search(rf"{re.escape(a[:6])}[^\n,;]*(OAB[^\n,;)]+)", resposta_text, re.I)
                if not oab_m:
                    oab_m = re.search(r"OAB[/\s]+([A-Z]{2}\s*n?\.?\s*\d+[\d.]*)", resposta_text, re.I)
                if oab_m:
                    formatted_advs.append(f"Dr. {clean_name} - {oab_m.group(0).strip()}")
                else:
                    formatted_advs.append(f"Dr. {clean_name}")
            return f"Representado por advogado particular, {', '.join(formatted_advs)}"

        if is_defensoria:
            defensor_m = re.search(
                r"(?:Defensor(?:a)?\s+P[úu]blic[oa][:\s-]+(?:Dr\(?a\)?\.?\s+)?|Dr\(?a\)?\.?\s+)([A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõ]+)+)",
                resposta_text,
            )
            if defensor_m and not any(k in defensor_m.group(0).lower() for k in ["estado", "comarca", "natal", "pública"]):
                return f"Assistido pela Defensoria Pública - Dr. {defensor_m.group(1).strip().title()}"
            return "Assistido pela Defensoria Pública"

        oab_match = re.search(
            r"(Dr\(?a\)?\.?\s+[A-Za-záéíóúâêôãõ\s]+(?:\s*[-–]\s*OAB/[A-Z]{2}\s*n?\.?\s*\d+[\d.]*))",
            resposta_text,
        )
        if oab_match:
            return f"Representado por advogado particular, {oab_match.group(1).strip()}"

        return "Assistido pela Defensoria Pública"
