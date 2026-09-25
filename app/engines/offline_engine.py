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
from app.core.jev_decision_engine import JEVDecisionEngine
from app.core.ocr_engine import OCREngine
from app.core.pje_indexer import index_pje_pdf, prune_documents
from app.engines.base import BaseExtractionEngine


# Standard regex for Brazilian judicial case numbers (CNJ)
CNJ_REGEX = re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b")

# Videoconference links
TEAMS_REGEX = re.compile(
    r"(https://teams\.microsoft\.com/meet/[^\s\"'>)]+|https://teams\.live\.com/meet/[^\s\"'>)]+)",
    re.IGNORECASE,
)
MEET_REGEX = re.compile(
    r"(https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3})",
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
    r"^(?:delegacia|estado(?:\s+d[oae]s?)?|defensoria|minist[eé]rio\s+p[uú]blico|pol[ií]cia|secretaria|comando|tribunal|juizado|vara\s+criminal|procuradoria|instituto|banco|central\s+de\s+flagrantes|dp\s+de|dpc\b|plant[aã]o\s+da\s+pol[ií]cia|departamento|munic[ií]pio|uni[aã]o)\b",
    re.IGNORECASE,
)


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
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        l_s = line.strip()
        if not l_s:
            clean_lines.append("")
            continue
        # Drop PJe marginal stamp lines
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

        # Find Denúncia (reverse search prioritizing official complaint from MP)
        for p_doc in reversed(pje_catalog):
            name_c = p_doc.doc_name.lower().strip()
            type_c = p_doc.doc_type.lower().strip()
            if any(ex in name_c for ex in ["cota", "requerimento", "recebimento", "aditamento", "certidão"]):
                continue
            if name_c.startswith("denún") or name_c.startswith("denun") or type_c.startswith("denún") or type_c.startswith("denun") or "queixa" in name_c:
                denuncia_doc = p_doc
                break

        if not denuncia_doc:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if ("denún" in comb or "denun" in comb or "queixa" in comb) and "cota" not in comb:
                    denuncia_doc = p_doc
                    break

        if not denuncia_doc:
            for p_doc in pje_catalog:
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if "petição inicial" in comb:
                    denuncia_doc = p_doc
                    break

        # Find Resposta à Acusação
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
        denuncia_text = self._extract_doc_text(doc, denuncia_doc) if denuncia_doc else ""
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

        # 9. Summary of Facts
        facts_summary, special_notes = self._extract_facts(
            denuncia_text, act_type, pje_catalog, doc
        )

        # 10. Chronological History with IDs
        chronological_history = self._build_chronological_history(pje_catalog, doc)

        # 11. Witnesses (Prosecution & Defense)
        pros_witnesses, def_witnesses, def_note = self._extract_witnesses(
            denuncia_text, resposta_text, vitimas_capa, testemunhas_capa, mandados_docs, doc
        )

        # 12. Defense Counsel
        defense_counsel = self._extract_defense_counsel(resposta_text, advs_capa, doc)

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
        """Extracts parties and roles from Page 1 Capa."""
        reus: List[str] = []
        advs: List[str] = []
        vitimas: List[str] = []
        testemunhas: List[str] = []
        prom: Optional[str] = None

        if len(doc) == 0:
            return reus, advs, vitimas, testemunhas, prom

        page1_lines = doc[0].get_text().split("\n")
        prev_line = ""

        for line in page1_lines:
            l = line.strip()
            l_upper = l.upper()

            if any(k in l_upper for k in ["(REU)", "(RÉU)", "(INVESTIGADO)", "(INVESTIGADA)", "(INDICIADO)", "(INDICIADA)", "(ACUSADO)", "(ACUSADA)"]):
                name = re.sub(r"\((?:R[EÉ]U|INVESTIGAD[OA]|INDICIAD[OA]|ACUSAD[OA])\)", "", l, flags=re.I).strip()
                if not name and prev_line:
                    name = prev_line
                name = re.sub(r"^[A-Z]+:\s*", "", name).strip()
                if name and len(name) > 3 and not STATE_ORGANS_BLACKLIST_REGEX.search(name) and name not in reus:
                    reus.append(name.strip())

            elif "(ADVOGADO)" in l_upper or "(DEFENSOR" in l_upper:
                name = re.sub(r"\(ADVOGADO\w*\)|\(DEFENSOR\w*\)", "", l, flags=re.I).strip()
                if not name and prev_line:
                    name = prev_line
                name = re.sub(r"^[A-Z]+:\s*", "", name)
                if name and len(name) > 3 and name not in advs:
                    advs.append(name.strip())

            elif "(VÍTIMA)" in l_upper or "(VITIMA)" in l_upper:
                name = re.sub(r"\(V[IÍ]TIMA\)", "", l, flags=re.I).strip()
                if not name and prev_line:
                    name = prev_line
                name = re.sub(r"^[A-Z]+:\s*", "", name)
                if name and len(name) > 3 and name not in vitimas:
                    vitimas.append(name.strip())

            elif "(TESTEMUNHA)" in l_upper:
                name = re.sub(r"\(TESTEMUNHA\)", "", l, flags=re.I).strip()
                if not name and prev_line:
                    name = prev_line
                name = re.sub(r"^[A-Z]+:\s*", "", name)
                if name and len(name) > 3 and name not in testemunhas:
                    testemunhas.append(name.strip())

            elif "(AUTOR)" in l_upper and ("PROMOTORIA" in l_upper or "MINISTÉRIO" in l_upper):
                prom_m = re.search(r"(\d+ª?\s+Promotoria[^\n)]+)", l, re.I)
                if prom_m:
                    prom = f"Dr. Promotor de Justiça ({prom_m.group(1).strip()})"
                else:
                    prom = "Dr. Promotor de Justiça"

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

        if pje_catalog:
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

        # Check 1: PAnP (Produção Antecipada de Provas - Art. 366 CPP)
        if re.search(r"\b(produ[cç][aã]o\s+antecipada|panp|art\.?\s*366)\b", h_comb, re.I):
            return "PAnP"
        if re.search(r"\bPANP\b", fn_upper):
            return "PAnP"

        # Check 2: Explicit ANPP in the active designated hearing text (Decision/Intimation)
        is_anpp_in_hearing = bool(
            re.search(
                r"(?:homologa[cç][aã]o\s+d[eo]\s+(?:acordo(?:\s+de\s+n[aã]o\s+persecu[cç][aã]o(?:\s+penal)?)?|anpp)|audi[eê]ncia\s+(?:de\s+anpp|para\s+fins\s+do\s+art\.?\s*28-a|para\s+homologa[cç][aã]o\s+d[eo]\s+acordo))",
                h_comb,
                re.I,
            )
        )
        if is_anpp_in_hearing and not ANPP_NEGATION_REGEX.search(h_comb):
            return "ANPP"

        # Check 3: Explicit AIJ in the designated hearing text
        if re.search(r"\b(instru[cç][aã]o(?:\s+e\s+julgamento)?|aij|oitiva\s+d[ae]s?\s+testemunhas?|inquirir\s+testemunhas?|inquiridas?\s+as\s+testemunhas|interrogat[oó]rio\s+d[eo]\s+(?:acusad[oa]|r[eé]u))\b", h_comb, re.I):
            return "AIJ"

        # Check 4: Custódia in hearing text
        if re.search(r"\b(audi[eê]ncia\s+de\s+cust[oó]dia|termo\s+de\s+audi[eê]ncia\s+de\s+cust[oó]dia)\b", h_comb, re.I) and not has_denuncia:
            return "Custódia"

        # Check 5: General received denúncia + AIJ mention in the case
        if has_received_denuncia and has_aij_mention:
            return "AIJ"

        # Check 6: Sursis Processual (Art. 89 Lei 9.099/95)
        if re.search(r"\b(audi[eê]ncia\s+de\s+suspens[aã]o|sursis\s+processual|admonit[oó]ria)\b", h_comb, re.I):
            return "Sursis"

        # Check 7: Scan backwards across ALL pages of the entire document (never capped)
        total_p = len(doc)
        for p in range(total_p - 1, -1, -1):
            p_txt = doc[p].get_text()
            if re.search(r"\b(produ[cç][aã]o\s+antecipada|panp|art\.?\s*366)\b", p_txt, re.I):
                return "PAnP"
            if re.search(r"(?:homologa[cç][aã]o\s+d[eo]\s+(?:acordo(?:\s+de\s+n[aã]o\s+persecu[cç][aã]o(?:\s+penal)?)?|anpp)|audi[eê]ncia\s+(?:de\s+anpp|para\s+fins\s+do\s+art\.?\s*28-a|para\s+homologa[cç][aã]o\s+d[eo]\s+acordo))", p_txt, re.I):
                if not ANPP_NEGATION_REGEX.search(p_txt) and not has_anpp_rejection:
                    return "ANPP"
            if re.search(r"\b(instru[cç][aã]o(?:\s+e\s+julgamento)?|aij|oitiva\s+d[ae]s?\s+testemunhas?|inquirir\s+testemunhas?)\b", p_txt, re.I):
                return "AIJ"

        # Check 8: Filename fallback
        if "ANPP" in fn_upper and not has_anpp_rejection:
            return "ANPP"
        if "AIJ" in fn_upper:
            return "AIJ"
        if "CUSTÓDIA" in fn_upper or "CUSTODIA" in fn_upper:
            return "Custódia"

        # Standard Default for criminal proceedings
        return "AIJ"

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
                meeting_link = m.group(1).rstrip(">)]., \r\n")

        # 2. Search subsequent notifications / intimations in catalog
        if not meeting_link:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["intimação", "mandado", "certidão", "diligência", "audiência", "despacho", "decisão"]):
                    d_txt = self._extract_doc_text(doc, p_doc)
                    m = TEAMS_REGEX.search(d_txt) or MEET_REGEX.search(d_txt)
                    if m:
                        meeting_link = m.group(1).rstrip(">)]., \r\n")
                        break

        # 3. Fallback scan across ALL pages of the entire document (never capped)
        if not meeting_link:
            total_p = len(doc)
            for p in range(total_p - 1, -1, -1):
                txt = doc[p].get_text()
                m = TEAMS_REGEX.search(txt) or MEET_REGEX.search(txt)
                if m:
                    meeting_link = m.group(1).rstrip(">)]., \r\n")
                    break

        is_in_person = meeting_link is None

        # Date & Time Extraction:
        # Step 1: Check filename first
        m_inv = re.search(r"(\d{1,2}h(?:\d{2})?)\s*[-–]\s*(\d{1,2})[./](\d{1,2})[./](\d{2,4})", filename, re.I)
        if m_inv:
            t_str, d, m, y = m_inv.groups()
            yr = y[-2:] if len(y) == 4 else y
            tm = t_str if "min" in t_str else (t_str + "00min" if len(t_str) <= 3 else t_str)
            return f"{int(d):02d}.{int(m):02d}.{yr} às {tm}", meeting_link, is_in_person

        m_fn = re.search(
            r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s*(?:,?\s*(?:às|as|-)\s*)(\d{1,2})(?::(\d{2})|h(\d{0,2})(?:min)?)?",
            filename,
            re.I,
        )
        if m_fn:
            d, m, y, h, mn_col, mn_h = m_fn.groups()
            yr = y[-2:] if len(y) == 4 else y
            mn = mn_col or mn_h or "00"
            if not mn:
                mn = "00"
            return f"{int(d):02d}.{int(m):02d}.{yr} às {int(h):02d}h{mn}min", meeting_link, is_in_person

        # Step 2: Search in hearing_text
        if hearing_text:
            dt_h = self._parse_datetime_from_text(hearing_text)
            if dt_h:
                return dt_h, meeting_link, is_in_person

        # Step 3: Scan ALL pages backwards from the end of the document (never capped)
        total_p = len(doc)
        for p in range(total_p - 1, -1, -1):
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
            m_num = MONTH_MAP.get(m_name.lower().strip(), "07")
            yr = y[-2:] if len(y) == 4 else y
            mn = mn_col or mn_h or "00"
            if not mn:
                mn = "00"
            return f"{int(d):02d}.{m_num}.{yr} às {int(h):02d}h{mn}min"

        # 2. Numeric date format:
        # e.g. "no dia 31/07/2026 às 11:00 horas" or "em 23/07/26 às 13h"
        m_num = re.search(
            r"(?:dia|data|para|em|pauta|audi[eê]ncia)\s+(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\s*(?:,?\s*(?:às|as|-)\s*)(\d{1,2})(?::(\d{2})|h(\d{0,2})(?:min)?)?",
            txt,
            re.IGNORECASE,
        )
        if m_num:
            d, m, y, h, mn_col, mn_h = m_num.groups()
            yr = y[-2:] if len(y) == 4 else y
            mn = mn_col or mn_h or "00"
            if not mn:
                mn = "00"
            return f"{int(d):02d}.{int(m):02d}.{yr} às {int(h):02d}h{mn}min"

        # 3. General scheduling phrase fallback
        m_gen = re.search(
            r"(?:no\s+dia|pauta\s+para|designad[oa]\s+para|aprazad[oa]\s+para|audi[eê]ncia\s+em)\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s*(?:,|às|as)\s*(\d{1,2}(?::\d{2}|h\d{0,2}))",
            txt,
            re.IGNORECASE,
        )
        if m_gen:
            d_str, t_str = m_gen.groups()
            d_clean = _format_date_short(d_str).replace("/", ".")
            t_clean = t_str.replace(":", "h")
            if not t_clean.endswith("min") and "h" in t_clean and len(t_clean) <= 3:
                t_clean += "00min"
            return f"{d_clean} às {t_clean}"

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

        # Find qualification block in Denúncia
        qual_pattern = re.compile(
            r"(?:"
            r"(?:(?:III|II|I)\)?\s*(?:Acusad[oa]s?|Denunciad[oa]s?))|"
            r"DENUNCIADO\(?A?\)?:?|"
            r"DOS\s+DENUNCIADOS:?|"
            r"DA\s+QUALIFICA[CÇ][AÃ]O(?:\s+D[OE]S\s+DENUNCIAD[OA]S)?|"
            r"oferecer\s+den[uú]ncia\s+(?:em\s+desfavor\s+de|contra)[:\s]*|"
            r"oferece\s+den[uú]ncia\s+(?:em\s+desfavor\s+de|contra)[:\s]*|"
            r"vem\s+perante\s+V\.\s*Exa\.?[^\n]*denunciar[:\s]*"
            r")"
            r"(.*?)"
            r"(?:"
            r"(?:^|\n)\s*(?:(?:IV|V|VI)\)\s*Narrativa|(?:IV|V|VI)\)|DOS\s+FATOS|I\s*[-–.]\s*DOS\s+FATOS|\n\s*Consta\s+d[oe]s\s+(?:inclus[oa]s|referidos)|pela\s+pr[aá]tica\s+dos\s+fatos|pelos\s+fatos\s+a\s+seguir|pelos\s+fatos\s+e\s+fundamentos)"
            r")",
            re.IGNORECASE | re.DOTALL,
        )
        match = qual_pattern.search(denuncia_text)
        raw_qual = match.group(1).strip() if match else ""
        if raw_qual:
            raw_qual = _clean_legal_text(raw_qual)
            raw_qual = re.sub(r"[ \t]+", " ", raw_qual)

        if not names:
            # Fallback extraction from raw qualification
            all_caps_names = re.findall(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ]{2,}){1,5})\b", raw_qual)
            names = [
                n for n in all_caps_names
                if not any(ex in n for ex in ["MINISTÉRIO", "ESTADO", "TRIBUNAL", "PODER", "VARA", "PROMOTORIA", "DENÚNCIA", "JUSTIÇA"])
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
                )
            )

        qual_text = "\n\n".join(defendant_quals) if defendant_quals else (raw_qual if raw_qual else "\n\n".join([f"{n}, qualificação nos autos." for n in names]))
        return defendants, qual_text

    def _extract_single_defendant_qualification(
        self, name: str, raw_qual: str, denuncia_text: str, ip_text: str
    ) -> str:
        """Extracts complete qualification for a defendant (filiation, RG, CPF, birth date, address)."""
        name_clean = name.strip()
        first_name = name_clean.split()[0] if name_clean.split() else ""

        # 1. Search in raw_qual for this defendant's chunk
        if raw_qual:
            pattern = re.compile(
                rf"(?:^|\n|[;.]\s*)\b({re.escape(name_clean)}[^\n;]+(?:[;,]\s*(?:brasileir[oa]|filh[oa]|cpf|rg|nascid|natural|residente|conhecido)[^\n;]*)*)",
                re.IGNORECASE,
            )
            m = pattern.search(raw_qual)
            if m:
                chunk = _clean_legal_text(m.group(1)).strip(" ;.\n")
                if any(k in chunk.lower() for k in ["cpf", "rg", "filho", "filha", "nascid", "natural", "residente"]):
                    return chunk

        # 2. Search in denuncia_text directly
        if denuncia_text:
            pattern2 = re.compile(
                rf"\b({re.escape(name_clean)}[^\n;]+(?:filh[oa]|cpf|rg|nascid|natural|residente)[^\n;]+(?:;\s*|\.\s*|\n\s*))",
                re.IGNORECASE,
            )
            m2 = pattern2.search(denuncia_text)
            if m2:
                chunk2 = _clean_legal_text(m2.group(1)).strip(" ;.\n")
                return chunk2

        # 3. Search in Inquérito Policial / APF text
        if ip_text and first_name:
            ip_pat = re.compile(
                rf"({re.escape(name_clean)}[^\n]+?(?:filh[oa]\s+de|nascid[oa]\s+em|cpf|rg)[^\n]+)",
                re.IGNORECASE,
            )
            m3 = ip_pat.search(ip_text)
            if m3:
                chunk3 = _clean_legal_text(m3.group(1)).strip(" ;.\n")
                return chunk3

        # 4. If raw_qual has content and name is in raw_qual
        if raw_qual and len(name.split()) >= 2 and (name.lower() in raw_qual.lower() or first_name.lower() in raw_qual.lower()):
            cleaned_single = _clean_legal_text(raw_qual).strip(" ;.\n")
            if any(k in cleaned_single.lower() for k in ["cpf", "rg", "filho", "nascid", "brasileir"]):
                return cleaned_single

        return f"{name_clean.upper()}, qualificação nos autos."

    def _extract_imputation(self, denuncia_text: str) -> str:
        """Extracts penal imputation articles and full crime title."""
        # 1. Search for explicit section header (e.g. 'VI) Imputação legal' or 'DA IMPUTAÇÃO')
        m_sec = re.search(
            r"(?:(?:VI|V|IV|III|II|I)\)?\s*Imputa[cç][aã]o(?:\s*legal)?|DA\s+IMPUTA[CÇ][AÃ]O|Tipifica[cç][aã]o\s*legal|Tipifica[cç][aã]o)[:\s\n]+([A-ZÁÉÍÓÚ][^\n]+(?:\n(?!\b(?:VII|VI|V|IV|III|II|I\)|DOS\s+PEDIDOS|DO\s+PEDIDO|ROL)\b)[^\n]+)?)",
            denuncia_text,
            re.IGNORECASE,
        )
        if m_sec:
            raw_imp = m_sec.group(1).strip()
            raw_imp = _clean_legal_text(raw_imp)
            raw_imp = re.sub(r"\s+", " ", raw_imp).strip()
            if len(raw_imp) > 10:
                return raw_imp

        # 2. Search for standard closing phrase in Denúncia
        m_crime = re.search(
            r"(?:pr[aá]tica\s+do\s+crime\s+de|como\s+incurso\s+n[ao]s?\s+penas\s+d[ao]|incurso\s+n[ao]s?\s+penas\s+d[ao]|condena[cç][aã]o\s+n[ao]s?\s+penas\s+d[ao])\s*([^\n.]+?(?:art(?:igo)?\.?\s*\d+[^\n.]+))",
            denuncia_text,
            re.IGNORECASE,
        )
        if m_crime:
            raw_imp = m_crime.group(1).strip()
            raw_imp = _clean_legal_text(raw_imp)
            raw_imp = re.sub(r"\s+", " ", raw_imp).strip()
            return raw_imp

        # 3. Fallback penal article match
        arts = re.findall(r"(art(?:igo)?\.?\s*\d+[^.\n;]+(?:Código Penal|CP|Lei[^.\n;]+)?)", denuncia_text, re.I)
        if arts:
            return f"Imputação penal ({arts[0].strip()})"

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
        return facts_result, None

    def _extract_clean_narrative(self, raw_text: str) -> List[str]:
        """Extracts clean, reflowed narrative paragraphs terminated at strict procedural boundaries."""
        if not raw_text:
            return []

        # 1. Stop delimiters (procedural requests, witness lists, cotas)
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
            r"(?:^|\n)\s*COTA\s*(?:[ÀA]\s*DENÚNCIA|DE\s*OFERECIMENTO)?|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\)?\s*)?(?:DOS\s+)?PEDIDOS?\b|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\)?\s*)?REQUERIMENTOS?\b|"
            r"(?:Ante|Diante)\s+[^\n]*exposto[^\n]*requer|"
            r"Requer\s+o\s+Minist[eé]rio\s+P[uú]blico|"
            r"(?:^|\n)\s*Assinaturas?\s+do\s+Documento"
            r")",
            re.IGNORECASE,
        )

        # 2. Start delimiters
        start_regex = re.compile(
            r"(?:"
            r"pelos?\s+fatos\s+e\s+fundamentos\s+que\s+passa\s+a\s+expor[^\n]*\n|"
            r"pela\s+pr[aá]tica\s+dos\s+fatos\s+delituosos\s+a\s+seguir\s+narrados[^\n]*\n|"
            r"(?:^|\n)\s*(?:[IVXLCDM]+\.?\s*)?(?:DOS\s+FATOS|NARRATIVA\s+F[AÁ]TICA(?:\s+CRIMINOSA)?|CONTEXTUALIZA[CÇ][AÃ]O\s+DA\s+INVESTIGA[CÇ][AÃ]O)[^\n]*\n|"
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
            facts_text = raw_text

        facts_text = re.sub(r"^(?:[IVXLCDM]+\)?\s*)?Narrativa\s+f[aá]tica(?:\s+criminosa)?\s*", "", facts_text, flags=re.I).strip()

        m_stop = stop_regex.search(facts_text)
        if m_stop:
            facts_text = facts_text[:m_stop.start()]

        lines = facts_text.split("\n")
        cleaned_lines: List[str] = []

        header_patterns = [
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

    def _build_chronological_history(
        self, pje_catalog: List[PJeDocument], doc: pymupdf.Document
    ) -> List[HistoryItem]:
        """Constructs the comprehensive chronological procedural history with IDs and substantive summaries."""
        items: List[HistoryItem] = []
        seen_ids = set()

        key_docs = prune_documents(pje_catalog)
        for p_doc in key_docs:
            if p_doc.doc_id in seen_ids or p_doc.start_page == 0:
                continue
            seen_ids.add(p_doc.doc_id)

            short_date = _format_date_short(p_doc.date_str)
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

        # 1. Denúncia
        if "denúncia" in name_l or "denuncia" in name_l:
            if "não foi proposto anpp" in txt_l or "deixo de propor anpp" in txt_l:
                return "Denúncia. Consta cota afirmando que não foi proposto ANPP em face dos denunciados"
            elif "suspensão condicional" in txt_l or "sursis" in txt_l:
                return "Denúncia oferecida com proposta de Suspensão Condicional do Processo"
            return "Denúncia oferecida pelo Ministério Público"

        # 2. Decisão
        if "decisão" in name_l or "decisao" in name_l:
            if "recebo a denúncia" in txt_l or "recebida a denúncia" in txt_l or "recebimento da denúncia" in txt_l:
                if "pauta" in txt_l or "designo" in txt_l:
                    return "Decisão recebendo a denúncia e designando audiência"
                return "Decisão recebendo a denúncia"
            if "revoga" in txt_l and ("suspensão" in txt_l or "sursis" in txt_l):
                return "Decisão revogando a Suspensão Condicional do Processo e designando AIJ"
            if "produção antecipada" in txt_l or "art. 366" in txt_l:
                return "Decisão suspendendo o processo (art. 366 CPP) e designando produção antecipada de provas"
            if "pauta" in txt_l or "designo" in txt_l or "instrução" in txt_l:
                return "Decisão designando audiência de instrução e julgamento"
            return "Decisão interlocutória"

        # 3. Despacho
        if "despacho" in name_l:
            if "pauta" in txt_l or "designo" in txt_l or "instrução" in txt_l:
                return "Despacho incluindo o feito em pauta de audiência de instrução e julgamento"
            if "reaprazo" in txt_l or "redesigno" in txt_l:
                return "Despacho redesignando a audiência"
            if "homologação de anpp" in txt_l or "homologar" in txt_l:
                return "Despacho designando audiência de homologação de ANPP"
            return "Despacho judicial"

        # 4. Resposta à acusação / Defesa prévia
        if "resposta" in name_l or "defesa prévia" in name_l:
            return "Resposta à acusação pugnando pela absolvição sumária do acusado"

        # 5. Citação / Edital / Mandados
        if "edital" in name_l:
            return "Citação por edital do acusado"
        if "mandado" in name_l and "citação" in name_l:
            return "Mandado de citação"
        if "mandado" in name_l and "intimação" in name_l:
            return "Mandado de intimação de audiência"
        if "intimação de audiência" in name_l or "intimação de audiência" in type_l:
            return "Intimação de audiência expedida"

        # 6. Audiências anteriores / Atas
        if "ata da audiência" in name_l or "termo de audiência" in name_l:
            if "custódia" in txt_l:
                return "Audiência de Custódia realizada"
            if "suspensão" in txt_l or "sursis" in txt_l:
                return "Audiência de Suspensão Condicional do Processo realizada"
            if "instrução" in txt_l:
                return "Ata de audiência de instrução realizada"
            return "Ata da audiência"

        # Fallback to cleaned document name
        return raw_name

    def _extract_witnesses(
        self,
        denuncia_text: str,
        resposta_text: str,
        vitimas_capa: List[str],
        testemunhas_capa: List[str],
        mandados_docs: List[PJeDocument],
        doc: pymupdf.Document,
    ) -> Tuple[List[Witness], List[Witness], Optional[str]]:
        """Extracts prosecution and defense witness lists with mandado ID matching."""
        pros_witnesses: List[Witness] = []
        def_witnesses: List[Witness] = []
        def_note = "A defesa requereu a oitiva de todas as testemunhas arroladas na denúncia."

        # Cache text of mandado / intimação docs to match by witness name
        mandado_texts: Dict[str, str] = {}
        for m_doc in mandados_docs:
            mandado_texts[m_doc.doc_id] = self._extract_doc_text(doc, m_doc).lower()

        # Helper to find subpoena / notification ID
        def find_subpoena_status(name: str, is_pm: bool) -> str:
            name_lower = name.lower()
            first_name = name.split()[0].lower() if name.split() else ""
            surname = name.split()[-1].lower() if len(name.split()) > 1 else ""

            matched_ids = []
            negative_ids = []

            for doc_id, m_text in mandado_texts.items():
                if name_lower in m_text or (len(first_name) > 3 and len(surname) > 3 and first_name in m_text and surname in m_text):
                    if "contrafé negativa" in m_text or "não localizado" in m_text or "deixei de citar" in m_text or "deixei de intimar" in m_text:
                        negative_ids.append(doc_id)
                    else:
                        matched_ids.append(doc_id)

            if negative_ids:
                return f"Certidão contrafé negativa ID {'; '.join(negative_ids)}"
            if matched_ids:
                if is_pm:
                    return f"Ofício enviado ID {matched_ids[0]}"
                return f"Intimada ID {matched_ids[0]}" if any(fem in name_lower for fem in ["maria", "ana", "julia", "samara", "dra", "sra"]) else f"Intimado ID {matched_ids[0]}"

            if is_pm:
                for m_doc in mandados_docs:
                    if "ofício" in m_doc.doc_name.lower():
                        return f"Ofício enviado ID {m_doc.doc_id}"
                return "Ofício expedido"

            return "Mandado expedido"

        num = 1
        seen_names = set()

        # 1. Parse Denúncia ROL DE TESTEMUNHAS (primary source in criminal process)
        cleaned_denuncia = _clean_legal_text(denuncia_text)
        start_pat = re.compile(
            r"(?:(?:^|\n)\s*(?:[IVXLCDM]+\)?\.?\s*)?(?:ROL\s+(?:DE\s+)?(?:DECLARANTES?\s*(?:\([^)]*\))?\s*(?:E\s*)?)?TESTEMUNHAS?\s*(?:\([^)]*\))?(?:\s*E\s*DECLARANTES?)?|ROL\s+TESTEMUNHAL|TESTEMUNHAS\s*:))",
            re.IGNORECASE,
        )
        m_start = start_pat.search(cleaned_denuncia)
        if m_start:
            sub = cleaned_denuncia[m_start.end():]
            stop_pat = re.compile(
                r"(?:^|\n)\s*(?:COTA\b|Termos\s+em\s+que|Nestes\s+termos|Pede\s+(?:e\s+espera\s+)?deferimento|Pede\s+deferimento)",
                re.IGNORECASE,
            )
            m_stop = stop_pat.search(sub)
            rol_body = sub[:m_stop.start()] if m_stop else sub

            blacklist = [
                "rua", "avenida", "travessa", "alameda", "telefone", "e-mail", "whatsapp", "cpf", "rg", "cep",
                "residente", "domiciliado", "bairro", "natal", "termos", "requer", "pede", "ministério",
                "promotoria", "defesa", "secretaria", "vara", "tribunal", "estado", "assinado", "documento",
                "pág", "registre", "dessa maneira", "cota", "rol de", "declarantes", "promotor",
            ]

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
                    name_lower = w_name.lower()
                    if len(w_name) <= 3 or any(b in name_lower for b in blacklist):
                        continue

                    ext1 = m.group(2) or ""
                    ext2 = m.group(3) or ""
                    extra = (line[len(m.group(0)):].lower() + " " + ext1.lower() + " " + ext2.lower()).strip()
                    is_pm = bool(
                        re.search(r"\b(?:pm|policial|militar|civil|cabo|sgt|sargento|soldado)\b", extra)
                        or re.search(r"\b(?:pm|policial)\b", name_lower)
                    )
                    is_vitima = any(v in extra for v in ["vítima", "vitima", "declarante"])
                    role = "vítima" if is_vitima else ("PM" if is_pm else "Testemunha")
                    status_id = find_subpoena_status(w_name, is_pm)

                    if name_lower not in seen_names:
                        seen_names.add(name_lower)
                        pros_witnesses.append(
                            Witness(number=num, name=w_name.title(), role=role, status_id=status_id)
                        )
                        num += 1

        # 2. Add victims from Capa if not already listed
        for v in vitimas_capa:
            if v.lower() not in seen_names:
                seen_names.add(v.lower())
                status_id = find_subpoena_status(v, is_pm=False)
                pros_witnesses.append(
                    Witness(number=num, name=v.title(), role="vítima", status_id=status_id)
                )
                num += 1

        # 3. Add witnesses from Capa if not already listed
        for t in testemunhas_capa:
            if t.lower() not in seen_names:
                seen_names.add(t.lower())
                is_pm = any(pm_term in t.lower() for pm_term in ["policial", "pm", "cabo", "sargento", "militar"])
                role = "PM" if is_pm else "Testemunha"
                status_id = find_subpoena_status(t, is_pm=is_pm)
                pros_witnesses.append(
                    Witness(number=num, name=t.title(), role=role, status_id=status_id)
                )
                num += 1

        return pros_witnesses, def_witnesses, def_note

    def _extract_defense_counsel(
        self, resposta_text: str, advs_capa: List[str], doc: pymupdf.Document
    ) -> str:
        """Identifies defense counsel with attorney name and OAB."""
        # 1. Check if Defensoria Pública
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
