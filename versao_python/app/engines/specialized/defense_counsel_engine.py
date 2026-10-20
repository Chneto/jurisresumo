# -*- coding: utf-8 -*-
"""Specialized Engine 5: Defense Representation & Counsel Engine (DefenseCounselEngine).

Responsible for:
1. Scanning catalog and text for all defense responses (named and inominada petitions).
2. Parsing defense petitions under arts. 396 and 396-A of CPP.
3. Identifying defense counsel (Defensoria Pública vs private attorney with OAB).
4. Mapping multiple defense attorneys to their respective defendants.
5. Synthesizing substantive defense arguments (preliminaries, summary acquittal, merits reservation).

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Optional
import pymupdf

from app.core.models import PJeDocument
from app.engines.specialized.common import (
    _clean_legal_text,
    _format_date_short,
    extract_doc_text,
)


class DefenseCounselEngine:
    """Specialized engine for defense representation, petitions parsing, and attorney mapping."""

    def find_all_defense_documents(
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

            txt = extract_doc_text(doc, p_doc)
            if not txt.strip():
                continue

            parsed = self.parse_defense_document(p_doc, txt, reus_capa, advs_capa, is_named_defense)
            if parsed:
                seen_ids.add(p_doc.doc_id)
                defense_docs.append(parsed)

        return defense_docs

    def parse_defense_document(
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
            else:
                clean_lawyer = ""
            clean_lawyer = lawyer_name
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

        from app.engines.specialized.witness_subpoena_engine import WitnessSubpoenaEngine
        explicit_witnesses = WitnessSubpoenaEngine().extract_defense_witness_names_from_text(text)

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

    def extract_defense_counsel(
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
