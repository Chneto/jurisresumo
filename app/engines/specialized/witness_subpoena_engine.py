# -*- coding: utf-8 -*-
"""Specialized Engine 10: Witness Extraction & Subpoena Linking Engine (WitnessSubpoenaEngine).

Responsible for:
1. Extracting prosecution witnesses from the accusatory complaint (Rol de Testemunhas).
2. Extracting defense witnesses from Resposta à Acusação petitions.
3. Classifying witness roles (Vítima, PM/Policial, Testemunha).
4. Cross-referencing witnesses with service records (mandados de intimação, ofícios a comandos, certidões negativas/positivas).
5. Performing unified deduplication and common-witness labeling:
   "(arrolada pelo Ministério Público e pela Defensoria Pública)" or "(arrolada por todos)".

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Optional, Tuple
import pymupdf

from app.core.models import PJeDocument, Witness
from app.engines.specialized.common import (
    _clean_legal_text,
    _normalize_witness_name,
    extract_doc_text,
)


class WitnessSubpoenaEngine:
    """Specialized engine for witness list extraction, subpoena cross-referencing, and unified deduplication."""

    def extract_witnesses(
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
                mandado_texts[m_doc.doc_id] = extract_doc_text(doc, m_doc).lower()

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
            if def_witnesses:
                def_note = None

        return pros_witnesses, def_witnesses, def_note

    def extract_defense_witness_names_from_text(self, text: str) -> List[str]:
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
