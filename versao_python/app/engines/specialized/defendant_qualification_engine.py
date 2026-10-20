# -*- coding: utf-8 -*-
"""Specialized Engine 6: Defendant Qualification & Status Engine (DefendantQualificationEngine).

Responsible for:
1. Extracting defendant names, filtering state organs.
2. Robust multiline qualification (filiation, RG, CPF, date of birth, residence).
3. Fallback to Inquérito Policial (IP/APF) when complaint is generic ("qualificado no IP").
4. Tracking detention facilities (penitenciária, cadeia pública, liberdade).
5. Matching citation (mandado de citação) and subpoena (mandado de intimação) PJe IDs.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Tuple
import pymupdf

from app.core.models import Defendant, PJeDocument
from app.engines.specialized.common import (
    STATE_ORGANS_BLACKLIST_REGEX,
    _clean_legal_text,
    _make_accent_tolerant_regex,
    extract_doc_text,
)


class DefendantQualificationEngine:
    """Specialized engine for defendant identification, qualification, and procedural status."""

    def extract_defendants_and_qual(
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
                ip_text += extract_doc_text(doc, ip_d) + "\n"

        if not names:
            names = ["RÉU A QUALIFICAR"]

        # Cache text of mandado / certidão / diligência docs to match by defendant name
        mandado_texts: Dict[str, str] = {}
        if doc is not None:
            for m_doc in mandados_docs:
                mandado_texts[m_doc.doc_id] = extract_doc_text(doc, m_doc).lower()

        # Check for prison facility across all pages
        full_pdf_prison = ""
        if doc is not None:
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
            d_qual = self.extract_single_defendant_qualification(name, raw_qual, denuncia_text, ip_text)
            defendant_quals.append(d_qual)

            # Detect prison status per individual defendant
            status = "respondendo ao processo em liberdade"
            d_qual_l = d_qual.lower()
            is_detained = (
                bool(re.search(r"\b(?:preso|presa|custodiad[oa]|penitenci[aá]ria|cadeia\s+p[uú]blica|cdp)\b", d_qual_l))
                and not re.search(r"\b(?:n[aã]o\s+(?:se\s+encontra\s+)?pres[oa]|solt[oa]|em\s+liberdade)\b", d_qual_l)
            )
            if not is_detained and full_pdf_prison and (len(names) == 1 or (len(first_name) > 3 and first_name in full_pdf_prison.lower())):
                is_detained = True

            if is_detained:
                is_female = (
                    any(fem in first_name for fem in ["maria", "ana", "julia", "carla", "patricia", "lucia", "claudia", "samara", "aline", "amanda", "bruna", "camila", "fernanda", "larissa", "leticia", "monica", "paula", "renata", "tatiana", "vanessa"])
                    or (first_name.endswith("a") and first_name not in ["luca", "lucas", "elias", "matias", "tobias"])
                )
                gender_prison = "ré presa" if is_female else "réu preso"
                if full_pdf_prison and (len(names) == 1 or (len(first_name) > 3 and first_name in full_pdf_prison.lower())):
                    status = f"{gender_prison}, atualmente {full_pdf_prison}"
                else:
                    status = gender_prison

            # Check decisions for suspension/edital specific to this defendant
            if "edital" in d_qual_l or "suspenso" in d_qual_l or (len(names) == 1 and ("citado por edital" in denuncia_text.lower() or "art. 366" in denuncia_text.lower())):
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

    def extract_single_defendant_qualification(
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
