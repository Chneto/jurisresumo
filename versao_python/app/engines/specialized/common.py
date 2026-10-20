# -*- coding: utf-8 -*-
"""Common helpers, constants, and regex patterns for specialized extraction engines.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Optional, Tuple
import pymupdf

from app.core.models import PJeDocument
from app.core.ocr_engine import OCREngine

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


def extract_doc_text(doc: pymupdf.Document, p_doc: Optional[PJeDocument]) -> str:
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
