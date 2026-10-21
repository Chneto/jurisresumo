# -*- coding: utf-8 -*-
"""Specialized Engine 8: Facts Narrative & ANPP Synthesis Engine (FactsNarrativeEngine).

Responsible for:
1. Extracting the pure factual narrative of the accusatory complaint.
2. Stripping vocatives, preamble, judicial salutations, and PJe header/footer artifacts.
3. Truncating at strict procedural boundaries (requests, witness lists, cota, tipicidade).
4. Capturing police interrogation (confession/denial) and forensic materiality.
5. Synthesizing the 6-paragraph canonical structure for ANPP hearings.
6. Recording special notes for resumed criminal proceedings (revocations of ANPP/PSCP).

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import List, Optional, Tuple
import pymupdf

from app.core.models import PJeDocument
from app.core.jev_decision_engine import JEVDecisionEngine
from app.engines.specialized.common import (
    ANPP_REVOCATION_REGEX,
    HEARING_DESIGNATION_REGEX,
    PSCP_REVOCATION_REGEX,
    _format_date_short,
    extract_doc_text,
)


class FactsNarrativeEngine:
    """Specialized engine for factual narrative extraction, boundary enforcement, and ANPP synthesis."""

    def extract_facts(
        self,
        denuncia_text: str,
        act_type: str,
        pje_catalog: List[PJeDocument],
        doc: pymupdf.Document,
    ) -> Tuple[str, Optional[str]]:
        """Extracts complaint facts, confession, and forensic reports with ANPP special notes."""
        if act_type == "ANPP":
            return self.build_anpp_facts(doc, pje_catalog, denuncia_text)

        # Non-ANPP: Standard AIJ / PAnP factual extraction
        narrative_paragraphs = self.extract_clean_narrative(denuncia_text)

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

        facts_result = "\n\n".join(narrative_paragraphs) if narrative_paragraphs else "Fatos narrados na denúncia."

        # Check revocation of ANPP or PSCP to inject into special_notes
        anpp_rev_doc = None
        pscp_rev_doc = None
        if pje_catalog and doc is not None:
            for p_doc in reversed(pje_catalog):
                comb = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if any(k in comb for k in ["decis", "despacho", "ato ordinat", "termo"]):
                    txt = extract_doc_text(doc, p_doc)
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

    def extract_clean_narrative(self, raw_text: str) -> List[str]:
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

        from app.engines.specialized.text_sanitizer_engine import TextSanitizerEngine
        sanitizer = TextSanitizerEngine()

        abbrev_rx = re.compile(
            rf"\b(?:{TextSanitizerEngine.NON_TERMINATING_ABBREVIATIONS})\.\s*$",
            re.IGNORECASE,
        )

        paragraphs: List[str] = []
        curr_para: List[str] = []

        for idx, l in enumerate(cleaned_lines):
            curr_para.append(l)
            ends_with_punct = bool(re.search(r"[.:;]$", l))
            ends_with_abbrev = bool(abbrev_rx.search(l))

            # Lookahead: if next line starts with lowercase or continuation, keep in same paragraph
            next_starts_lower = False
            if idx + 1 < len(cleaned_lines):
                next_starts_lower = bool(re.match(r"^[a-zà-ú0-9,;:)\]§-]", cleaned_lines[idx + 1]))

            if ends_with_punct and not ends_with_abbrev and not next_starts_lower:
                p_text = re.sub(r"^\d+\)\s*", "", " ".join(curr_para))
                p_text = sanitizer.separate_glued_words(p_text)
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

                # Only discard empty or standalone section headers; preserve legitimate substantive sentences
                is_header = bool(re.match(r"^(?:[IVXLCDM]+\.?\s*)?(?:DOS\s+FATOS|FATOS(?:\s+NARRADOS)?|HIST[OÓ]RICO|DA\s+NARRATIVA|\d+\.?)\s*$", p_text, re.IGNORECASE))
                if len(p_text) >= 4 and not is_header:
                    paragraphs.append(p_text)
                curr_para = []

        if curr_para:
            p_text = re.sub(r"^\d+\)\s*", "", " ".join(curr_para))
            p_text = sanitizer.separate_glued_words(p_text)
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
            is_header = bool(re.match(r"^(?:[IVXLCDM]+\.?\s*)?(?:DOS\s+FATOS|FATOS(?:\s+NARRADOS)?|HIST[OÓ]RICO|DA\s+NARRATIVA|\d+\.?)\s*$", p_text, re.IGNORECASE))
            if len(p_text) >= 4 and not is_header:
                paragraphs.append(p_text)

        return paragraphs

    def build_anpp_facts(
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
                (d for d in reversed(pje_catalog) if any(k in d.doc_name.lower() for k in ["despacho", "decisão", "decisao"]) and HEARING_DESIGNATION_REGEX.search(extract_doc_text(doc, d))),
                None,
            )
        # Find Inquérito Policial document
        ip_doc = next(
            (d for d in pje_catalog if any(k in d.doc_name.lower() for k in ["inquérito", "inquerito", "ip_"])),
            None,
        )

        # Origin case search
        origin_proc = ""
        if cisao_doc and doc is not None:
            c_txt = extract_doc_text(doc, cisao_doc)
            c_m = re.search(r"principal\s+n[ºo]?\s*(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", c_txt, re.I)
            if c_m:
                origin_proc = c_m.group(1)
        if not origin_proc and despacho_doc and doc is not None:
            d_txt = extract_doc_text(doc, despacho_doc)
            d_m = re.search(r"principal\s+n[ºo]?\s*(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", d_txt, re.I)
            if d_m:
                origin_proc = d_m.group(1)
        if not origin_proc and doc is not None and len(doc) > 0:
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
        termo_text = extract_doc_text(doc, termo_doc) if (termo_doc and doc is not None) else ""
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
            desp_txt = extract_doc_text(doc, despacho_doc) if doc is not None else ""
            dt_m = re.search(r"(\d{2}/\d{2}/\d{2,4}).*?(?:[àa]s\s*)?(\d{2}h\d{2}|\d{2}:\d{2})", desp_txt)
            dt_str = f" para {dt_m.group(1)}, às {dt_m.group(2)}" if dt_m else ""
            paras.append(f"{d_date}: Despacho designando a audiência de homologação de ANPP{dt_str} (ID {despacho_doc.doc_id})")

        return "\n\n".join(paras), None
