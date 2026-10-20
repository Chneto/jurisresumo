# -*- coding: utf-8 -*-
"""Specialized Engine 3: Hearing Designation & Details Engine (HearingDetailsEngine).

Responsible for:
1. Locating the judicial act of hearing designation (Decisão, Despacho, Termo).
2. Extracting the scheduled hearing date and time with standard format DD.MM.AA às HHhMMmin.
3. Extracting virtual hearing links (Microsoft Teams, Google Meet, lnk.tjrn.jus.br).
4. Determining whether the hearing is in-person (presencial) or virtual.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import List, Optional, Tuple
import pymupdf

from app.core.models import PJeDocument
from app.engines.specialized.common import (
    HEARING_DESIGNATION_REGEX,
    MEET_REGEX,
    MONTH_MAP,
    TEAMS_REGEX,
    extract_doc_text,
)


class HearingDetailsEngine:
    """Specialized engine for hearing scheduling, datetime parsing, and link detection."""

    def find_hearing_document(
        self,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
    ) -> Tuple[Optional[PJeDocument], str]:
        """Reverse searches catalog for the most recent hearing designation judicial act."""
        decisao_audiencia_doc = None
        hearing_text = ""

        # Priority search in candidate judicial acts
        for p_doc in reversed(pje_catalog):
            comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
            if any(ex in comb for ex in ["manual", "extrato", "dados telef", "comprovante", "foto", "laudo", "inquérito", "boletim"]):
                continue
            if any(k in comb for k in ["decis", "despacho", "ato ordinat", "audiência", "audiencia", "intimação", "mandado", "termo", "ata da audiência"]):
                txt = extract_doc_text(doc, p_doc)
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
                    hearing_text = extract_doc_text(doc, p_doc)
                    break

        return decisao_audiencia_doc, hearing_text

    def extract_hearing_details(
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
                    d_txt = extract_doc_text(doc, p_doc)
                    m = TEAMS_REGEX.search(d_txt) or MEET_REGEX.search(d_txt)
                    if m:
                        meeting_link = m.group(0).rstrip(">)]., \r\n")
                        break

        # 3. Fallback scan annotations and text in the last 25 pages
        if not meeting_link and doc is not None:
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
            dt_h = self.parse_datetime_from_text(hearing_text)
            if dt_h:
                return dt_h, meeting_link, is_in_person

        # Step 3: Search relevant hearing/mandado/intimação documents in catalog
        if doc is not None:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["audiência", "audiencia", "intimação", "mandado", "despacho", "decisão"]):
                    d_txt = extract_doc_text(doc, p_doc)
                    dt_d = self.parse_datetime_from_text(d_txt)
                    if dt_d:
                        return dt_d, meeting_link, is_in_person

        # Step 4: Fallback scan ONLY the last 5 pages of the document
        if doc is not None:
            total_p = len(doc)
            for p in range(total_p - 1, max(-1, total_p - 6), -1):
                txt = doc[p].get_text()
                dt_p = self.parse_datetime_from_text(txt)
                if dt_p:
                    return dt_p, meeting_link, is_in_person

        return "Data a definir", meeting_link, is_in_person

    def parse_datetime_from_text(self, txt: str) -> Optional[str]:
        """Extracts and formats hearing date and time from Portuguese text."""
        # 1. Portuguese format with month names:
        # e.g. "para o dia 17 (sexta-feira) de julho de 2026, às 09:00 horas"
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
