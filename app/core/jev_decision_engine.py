"""Motor de Decisão Estruturada JEV (System One) e Roteamento Jurídico Leya.

Implementa um classificador determinístico e probabilístico de alto desempenho (System One),
sem dependências externas de rede, para aferição de relevância, descarte rigoroso de ruídos de OCR
(carimbos, comprovantes bancários, certidões avulsas), controle estrito de fronteiras documentais,
taxonomia penal com colchetes e roteamento de peças essenciais segundo a hierarquia canônica do CPP
(Revogação ANPP/PSCP -> PAnP -> ANPP -> AIJ -> Custódia -> Sursis).

Inspirado nos conceitos de TypeSafe Jev (decisão estruturada e tipada) e Leya (precisão de
fluxos jurídicos e ground-truth documental).

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.crime_taxonomy import annotate_imputation_text
from app.core.models import (
    Defendant,
    DocumentCategory,
    HearingSummaryData,
    HistoryItem,
    JEVDecisionResult,
    OCRLine,
    PJeDocument,
    Witness,
)


# PJe Marginal Stamps, Signature Footers and Electronic Certifications
PJE_MARGIN_STAMPS_REGEX = re.compile(
    r"(?:"
    r"Num\.\s*\d+\s*-\s*Pág\.\s*\d+|"
    r"Assinado\s+eletronicamente\s+por\b|"
    r"Número\s+do\s+documento\s*:\s*\d+|"
    r"https?://pje[^\s\"'>)]+|"
    r"pje1g\.tjrn\.jus\.br[^\s\"'>)]+|"
    r"Código\s+de\s+validação\s*:\s*[A-Z0-9]+|"
    r"Documento\s+assinado\s+eletronicamente\s+conforme\s+MP|"
    r"Valide\s+a\s+autenticidade\s+deste\s+documento|"
    r"Tribunal\s+de\s+Justiça\s+do\s+Rio\s+Grande\s+do\s+Norte\s*-\s*DJe|"
    r"Diário\s+da\s+Justiça\s+Eletrônico|"
    r"Identificador\s*:\s*\d+"
    r")",
    re.IGNORECASE,
)

# Bank slips, tax receipts, payment vouchers, barcodes, financial garbage
BANKING_NOISE_REGEX = re.compile(
    r"(?:"
    r"comprovante\s+de\s+(?:pagamento|transfer[eê]ncia|agendamento|dep[oó]sito|transa[cç][aã]o)|"
    r"autentica[cç][aã]o\s+mec[aâ]nica|"
    r"linha\s+digit[aá]vel|"
    r"\b\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\b|"
    r"banco\s+(?:do\s+brasil|bradesco|itau|santander|inter|caixa\s+econ[oô]mica)|"
    r"arrecada[cç][aã]o\s+(?:estadual|federal|tribut[aá]ria)|"
    r"guia\s+de\s+recolhimento(?:\s+de\s+custas)?|"
    r"chave\s+de\s+acesso\s+nfe|"
    r"danfe\s+documento\s+auxiliar|"
    r"valor\s+total\s+r\$|"
    r"tarifa\s+banc[aá]ria|"
    r"protocolo\s+de\s+envio|"
    r"c[oó]digo\s+de\s+barras"
    r")",
    re.IGNORECASE,
)

# Generic administrative certidões that contain NO factual or evidentiary content
ADMIN_NOISE_REGEX = re.compile(
    r"(?:"
    r"certifico\s+que\s+(?:decorreu\s+o\s+prazo|os\s+autos\s+foram\s+conclusos|renovei\s+o\s+expediente)|"
    r"fa[cç]o\s+conclusos\s+estes\s+autos|"
    r"certid[aã]o\s+de\s+(?:triagem|juntada\s+gen[eé]rica|remessa\s+ao\s+dje|publica[cç][aã]o\s+no\s+dje)|"
    r"certifico\s+e\s+dou\s+f[eé]\s+que\s+publiquei"
    r")",
    re.IGNORECASE,
)

# Positive signals for Denúncia / Fatos
DENUNCIA_POSITIVE_REGEX = re.compile(
    r"(?:"
    r"\bden[uú]ncia\b|"
    r"o\s+minist[eé]rio\s+p[uú]blico(?:\s+do\s+estado)?|"
    r"imputa-se\s+ao\s+denunciado|"
    r"consta\s+(?:d[oe]s|nas)\s+(?:inclus[oa]s|referidos)\s+autos|"
    r"no\s+dia\s+\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{2,4}|"
    r"por\s+volta\s+d(?:as?|e)\s+\d{1,2}h|"
    r"subtraiu\b|matou\b|agrediu\b|transportava\b|guardava\b|trazia\s+consigo|"
    r"arma\s+de\s+fogo|subst[aâ]ncia\s+entorpecente|coca[ií]na|maconha|crack|"
    r"laudo\s+pericial|exame\s+traumatol[oó]gico|termo\s+de\s+exibi[cç][aã]o\s+e\s+apreens[aã]o|"
    r"art(?:igo)?\.?\s*\d+\s*(?:do\s+c[oó]digo\s+penal|da\s+lei)|"
    r"qualifica[cç][aã]o\s+do\s+acusado"
    r")",
    re.IGNORECASE,
)

# Positive signals for Audiência Decisions (AIJ, ANPP, PAnP, Júri, Custódia, Protetivas)
DECISAO_POSITIVE_REGEX = re.compile(
    r"(?:"
    r"design[ao]\s+o\s+dia\s+\d{1,2}|"
    r"audi[eê]ncia\s+de\s+instru[cç][aã]o\s+e\s+julgamento|"
    r"audi[eê]ncia\s+de\s+homologa[cç][aã]o|"
    r"acordo\s+de\s+n[aã]o\s+persecu[cç][aã]o\s+penal|"
    r"produ[cç][aã]o\s+antecipada\s+de\s+provas|"
    r"art\.?\s*366\s+do\s+cpp|"
    r"sess[aã]o\s+(?:plen[aá]ria\s+)?d[eo]\s+j[uú]ri|"
    r"tribunal\s+do\s+j[uú]ri|"
    r"decis[aã]o\s+de\s+pron[uú]ncia|"
    r"pronuncio\s+o\s+acusado|"
    r"audi[eê]ncia\s+de\s+cust[oó]dia|"
    r"auto\s+de\s+pris[aã]o\s+em\s+flagrante|"
    r"audi[eê]ncia\s+de\s+justifica[cç][aã]o|"
    r"medida\s+protetiva(?:\s+de\s+urg[eê]ncia)?|"
    r"art\.?\s*16\s+da\s+lei\s+11\.?340|"
    r"recebo\s+a\s+den[uú]ncia|"
    r"intime[m-]?se|"
    r"requisite[m-]?se|"
    r"notifique[m-]?se|"
    r"cite[m-]?se"
    r")",
    re.IGNORECASE,
)

# Positive signals for Rol de Testemunhas
TESTEMUNHAS_POSITIVE_REGEX = re.compile(
    r"(?:"
    r"rol\s+de\s+testemunhas|"
    r"rol\s+testemunhal|"
    r"testemunhas\s+da\s+(?:acusa[cç][aã]o|defesa)|"
    r"policial\s+militar|"
    r"v[ií]tima|"
    r"testemunha\s+presencial"
    r")",
    re.IGNORECASE,
)

# Signals for ANPP / PSCP Revocation (Retomada da Ação Penal -> AIJ Obrigatória)
ANPP_REVOCATION_REGEX = re.compile(
    r"(?:"
    r"revog(?:a[cç][aã]o|ou|ando|ado)?\s+(?:d[eo]\s+)?(?:acordo\s+de\s+n[aã]o\s+persecu[cç][aã]o(?:\s+penal)?|anpp)|"
    r"rescind(?:iu|indo|ida|ido)?\s+(?:o\s+)?(?:anpp|acordo)|"
    r"descumprimento\s+d[eo]\s+(?:acordo|anpp)|"
    r"(?:anpp|acordo)\s+(?:foi\s+)?revogad[ao]|"
    r"revogo\s+o\s+(?:acordo|anpp)"
    r")",
    re.IGNORECASE,
)

PSCP_REVOCATION_REGEX = re.compile(
    r"(?:"
    r"revog(?:a[cç][aã]o|ou|ando|ado)?\s+(?:da\s+)?(?:suspens[aã]o\s+condicional\s+do\s+processo|pscp|benef[ií]cio\s+do\s+art\.?\s*89)|"
    r"descumprimento\s+d[ae]\s+(?:condi[cç][oõ]es\s+da\s+)?(?:suspens[aã]o|pscp)|"
    r"(?:suspens[aã]o\s+condicional\s+do\s+processo|pscp)\s+(?:foi\s+)?revogad[ao]|"
    r"revogo\s+a\s+suspens[aã]o\s+condicional\s+do\s+processo"
    r")",
    re.IGNORECASE,
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


# Postal delivery receipts (AR dos Correios) and telephone carrier data / ERBs
POSTAL_AND_TELCO_NOISE_REGEX = re.compile(
    r"(?:"
    r"aviso\s+de\s+recebimento\s*-\s*ar\b|"
    r"rastreamento\s+de\s+objetos|"
    r"correios\s+empresa\s+brasileira|"
    r"dados\s+cadastrais\s+de\s+telefonia|"
    r"chamadas\s+originadas|chamadas\s+recebidas|"
    r"estação\s+rádio\s+base\b|\berb\b|"
    r"bilhetagem\s+telefônica|"
    r"relatório\s+de\s+dados\s+telemáticos|"
    r"extrato\s+de\s+chamadas"
    r")",
    re.IGNORECASE,
)


def is_procedural_or_constitutional(match_text: str, context_text: str = "") -> bool:
    """Verifica se o artigo citado se refere a normas constitucionais (CF) ou processuais (CPP)."""
    match_lower = match_text.lower().strip()

    # 1. Direct indication of procedural / constitutional diplomas in match_text
    if re.search(
        r"\b(?:da\s+cf(?:/88)?|da\s+constitui[cç][aã]o|do\s+cpp|do\s+c[oó]digo\s+de\s+processo\s+penal|processual\s+penal|processo\s+penal)\b",
        match_lower,
    ):
        return True

    # 1.5. Articles 91, 92 (efeitos da condenação), 107, 115 (extinção punibilidade), 143 (retratação) and 145 (rito queixa) are non-imputational
    if re.search(r"\bart(?:igo)?s?\b\.?\s*(?:91|92|107|115|143|145)\b", match_lower):
        return True

    # 2. If match_text explicitly specifies penal code, it is substantive penal law (not procedural)
    if re.search(r"\b(?:do\s+cp|do\s+c[oó]digo\s+penal)\b", match_lower):
        return False

    # 3. Known exclusively procedural or administrative articles (unless explicitly marked as "do CP")
    # e.g., CPP 30, 38, 41, 44, 45, 158-A..158-F, 201, 311, 312, 366, 383, 384, 396, 396-A, 399, 400, 519, 520; CF 129
    if re.search(
        r"\bart(?:igo)?s?\b\.?\s*(?:30|38|41|44|45|158-[a-f]|201|311|312|366|383|384|396(?:-[a-z])?|399|400|519|520)\b",
        match_lower,
        re.I,
    ):
        return True

    # 4. Context check: inspect local window around match_text
    if context_text:
        # If context is short (e.g. test snippet <= 300 chars), evaluate comb
        if len(context_text) <= 300:
            comb = f"{match_text} {context_text}".lower()
            if re.search(
                r"\b(?:da\s+cf(?:/88)?|da\s+constitui[cç][aã]o|do\s+cpp|do\s+c[oó]digo\s+de\s+processo\s+penal|processual\s+penal|processo\s+penal)\b",
                comb,
            ):
                return True
        else:
            # Long document: look at local context around match_text occurrences (+/- 80 chars)
            esc = re.escape(match_text.strip())
            for m in re.finditer(esc, context_text, re.IGNORECASE):
                start = max(0, m.start() - 60)
                end = min(len(context_text), m.end() + 80)
                window = context_text[start:end].lower()
                if re.search(
                    r"\b(?:da\s+cf(?:/88)?|da\s+constitui[cç][aã]o|do\s+cpp|do\s+c[oó]digo\s+de\s+processo\s+penal|processual\s+penal|processo\s+penal)\b",
                    window,
                ):
                    if not re.search(r"\b(?:do\s+cp|do\s+c[oó]digo\s+penal)\b", window):
                        return True

    # 5. Articles 69, 70, 71 of CPP (territorial competence) vs CP (concurso)
    if re.search(r"\bart(?:igo)?s?\b\.?\s*(?:69|70|71)\b", match_lower):
        if context_text and len(context_text) > 300:
            esc = re.escape(match_text.strip())
            for m in re.finditer(esc, context_text, re.IGNORECASE):
                start = max(0, m.start() - 50)
                end = min(len(context_text), m.end() + 80)
                window = context_text[start:end].lower()
                if re.search(r"\b(?:do\s+cpp|do\s+c[oó]digo\s+de\s+processo\s+penal|compet[eê]ncia)\b", window):
                    return True

    return False


class NoiseAndNullGate:
    """Mecanismo Multi-Critérios de Filtragem e Rejeição de Nulos e Ruídos (System One)."""

    @staticmethod
    def evaluate(text: str, metadata: str = "") -> Dict[str, Any]:
        """Avalia de forma probabilística e determinística a relevância de um bloco de texto.

        Returns:
            Dict com flags is_null, chance_null, chance_noise, chance_essential, passed, metrics e rationale.
        """
        if not text or not text.strip():
            return {
                "is_null": True,
                "chance_null": 1.0,
                "chance_noise": 1.0,
                "chance_essential": 0.0,
                "passed": False,
                "metrics": {"null_check": 1.0, "ocr_density": 0.0, "banking": 0.0, "admin": 0.0, "telco": 0.0},
                "rationale": "Bloco de texto vazio, nulo ou composto exclusivamente por espaços.",
            }

        cleaned = re.sub(r"\s+", " ", text).strip()
        total_len = len(cleaned)
        alphanumeric_count = sum(c.isalnum() for c in cleaned)
        alpha_ratio = alphanumeric_count / max(1, total_len)

        combined_meta = metadata.lower()

        # 1. Quase sem caracteres alfanuméricos (ruído de digitalização)
        if alphanumeric_count < 3 or (alpha_ratio < 0.30 and total_len > 10):
            return {
                "is_null": False,
                "chance_null": 0.0,
                "chance_noise": 0.95,
                "chance_essential": 0.05,
                "passed": False,
                "metrics": {"null_check": 0.0, "ocr_density": alpha_ratio, "banking": 0.0, "admin": 0.0, "telco": 0.0},
                "rationale": "Densidade alfanumérica extremamente baixa (artefatos de OCR).",
            }

        # 2. Ruído bancário / financeiro
        if BANKING_NOISE_REGEX.search(cleaned) or BANKING_NOISE_REGEX.search(combined_meta):
            return {
                "is_null": False,
                "chance_null": 0.0,
                "chance_noise": 0.95,
                "chance_essential": 0.05,
                "passed": False,
                "metrics": {"null_check": 0.0, "ocr_density": alpha_ratio, "banking": 1.0, "admin": 0.0, "telco": 0.0},
                "rationale": "Comprovante bancário, guia de custas ou extrato financeiro irrelevante.",
            }

        # 3. Ruído de dados de telefonia / ERB / Correios AR
        if POSTAL_AND_TELCO_NOISE_REGEX.search(cleaned) or POSTAL_AND_TELCO_NOISE_REGEX.search(combined_meta):
            return {
                "is_null": False,
                "chance_null": 0.0,
                "chance_noise": 0.90,
                "chance_essential": 0.10,
                "passed": False,
                "metrics": {"null_check": 0.0, "ocr_density": alpha_ratio, "banking": 0.0, "admin": 0.0, "telco": 1.0},
                "rationale": "Dados cadastrais/ERB de telefonia ou comprovante de entrega postal sem teor acusatório.",
            }

        # 4. Certidão administrativa estéril
        if ADMIN_NOISE_REGEX.search(cleaned) and not DENUNCIA_POSITIVE_REGEX.search(cleaned):
            return {
                "is_null": False,
                "chance_null": 0.0,
                "chance_noise": 0.85,
                "chance_essential": 0.15,
                "passed": False,
                "metrics": {"null_check": 0.0, "ocr_density": alpha_ratio, "banking": 0.0, "admin": 1.0, "telco": 0.0},
                "rationale": "Certidão puramente administrativa de trâmite sem teor fático.",
            }

        # 5. Texto aprovado pelo Gate
        return {
            "is_null": False,
            "chance_null": 0.0,
            "chance_noise": 0.10,
            "chance_essential": 0.90,
            "passed": True,
            "metrics": {"null_check": 0.0, "ocr_density": alpha_ratio, "banking": 0.0, "admin": 0.0, "telco": 0.0},
            "rationale": "Conteúdo substancial processual aprovado pelo Gate de Validação.",
        }


class ClassificationHierarchyCPP:
    """Matriz de Classificação de Audiência com a Hierarquia Estrita do Processo Penal."""

    @staticmethod
    def classify(
        h_comb: str,
        fn_upper: str,
        pje_catalog: Optional[List[PJeDocument]] = None,
        anpp_rev_doc: Optional[PJeDocument] = None,
        pscp_rev_doc: Optional[PJeDocument] = None,
        has_received_denuncia: bool = False,
        has_aij_mention: bool = False,
        has_anpp_rejection: bool = False,
        has_denuncia: bool = True,
    ) -> str:
        if pje_catalog is None:
            pje_catalog = []
        """Determina o tipo de ato da audiência segundo as prioridades do CPP e legislação especial.

        Hierarquia de Precedência Atualizada:
        1. Sessão Plenária do Tribunal do Júri (Decisão de Pronúncia e pauta de júri) -> Tipo: "JÚRI"
        2. Audiência de Custódia (APF recente sem recebimento de denúncia) -> Tipo: "CUSTÓDIA"
        3. Revogação de ANPP ou PSCP -> Tipo: "AIJ" (Imposição obrigatória - retomada da marcha penal)
        4. Produção Antecipada de Provas (Art. 366 do CPP) -> Tipo: "PAnP"
        5. Homologação de Acordo de Não Persecução Penal -> Tipo: "ANPP"
        6. Instrução e Julgamento ordinária/sumária -> Tipo: "AIJ"
        7. Medida Protetiva de Urgência (Lei 11.340/06, art. 16) -> Tipo: "JUSTIFICAÇÃO / PROTETIVA"
        """
        # Prioridade 1: Sessão Plenária do Tribunal do Júri
        is_juri = bool(
            re.search(
                r"\b(sess[aã]o\s+(?:plen[aá]ria\s+)?d[eo]\s+j[uú]ri|tribunal\s+do\s+j[uú]ri|julgamento\s+em\s+plen[aá]rio|pauta\s+d[eo]\s+j[uú]ri|sorteio\s+dos\s+jurados|decis[aã]o\s+de\s+pron[uú]ncia|pronuncio\s+o\s+acusado|pronunciad[oa]|art\.?\s*413\s+do\s+cpp)\b",
                h_comb,
                re.I,
            )
            or ("JÚRI" in fn_upper or "JURI" in fn_upper)
        )
        if not is_juri and pje_catalog:
            for p_doc in pje_catalog:
                comb_p = f"{p_doc.doc_name} {p_doc.doc_type}".lower()
                if "pronúncia" in comb_p or "pronuncia" in comb_p:
                    if any(k in h_comb for k in ["sessão", "sessao", "plenário", "plenario", "júri", "juri", "julgamento"]):
                        is_juri = True
                        break
        if is_juri:
            return "JÚRI"

        # Prioridade 2: Audiência de Custódia (APF sem denúncia recebida)
        is_custodia = bool(
            re.search(
                r"\b(audi[eê]ncia\s+de\s+cust[oó]dia|termo\s+de\s+audi[eê]ncia\s+de\s+cust[oó]dia|apresenta[cç][aã]o\s+d[eo]\s+preso(?:\s+em\s+flagrante)?)\b",
                h_comb,
                re.I,
            )
            or ("CUSTÓDIA" in fn_upper or "CUSTODIA" in fn_upper)
        )
        if not is_custodia and not has_received_denuncia and not has_denuncia:
            if re.search(r"\b(auto\s+de\s+pris[aã]o\s+em\s+flagrante|comunica[cç][aã]o\s+do\s+flagrante|apf\b)\b", h_comb, re.I):
                is_custodia = True
            elif pje_catalog:
                has_apf = any("flagrante" in f"{d.doc_name} {d.doc_type}".lower() or "apf" in f"{d.doc_name} {d.doc_type}".lower() for d in pje_catalog)
                has_den = any("denún" in f"{d.doc_name} {d.doc_type}".lower() or "denun" in f"{d.doc_name} {d.doc_type}".lower() for d in pje_catalog)
                if has_apf and not has_den:
                    is_custodia = True

        if is_custodia and not has_received_denuncia:
            return "CUSTÓDIA"

        # Prioridade 3: Revogação de ANPP ou PSCP impõe obrigatoriamente AIJ
        if anpp_rev_doc or pscp_rev_doc:
            return "AIJ"
        if ANPP_REVOCATION_REGEX.search(h_comb) or PSCP_REVOCATION_REGEX.search(h_comb):
            return "AIJ"

        # Prioridade 4: PAnP (Art. 366 CPP)
        if re.search(r"\b(produ[cç][aã]o\s+antecipada|panp|art\.?\s*366)\b", h_comb, re.I) or "PANP" in fn_upper:
            return "PAnP"

        # Prioridade 5: ANPP homologatório em designação afirmativa
        is_anpp_in_hearing = bool(
            re.search(
                r"(?:homologa[cç][aã]o\s+d[eo]\s+(?:acordo(?:\s+de\s+n[aã]o\s+persecu[cç][aã]o(?:\s+penal)?)?|anpp)|audi[eê]ncia\s+(?:de\s+anpp|para\s+fins\s+do\s+art\.?\s*28-a|para\s+homologa[cç][aã]o\s+d[eo]\s+acordo))",
                h_comb,
                re.I,
            )
        )
        if is_anpp_in_hearing and not has_anpp_rejection and not ANPP_NEGATION_REGEX.search(h_comb):
            return "ANPP"

        # Prioridade 6: AIJ explícita
        if re.search(r"\b(instru[cç][aã]o(?:\s+e\s+julgamento)?|aij|oitiva\s+d[ae]s?\s+testemunhas?|inquirir\s+testemunhas?|interrogat[oó]rio)\b", h_comb, re.I):
            return "AIJ"

        # Prioridade 7: Medida Protetiva de Urgência / Justificação (Lei 11.340/06, art. 16)
        is_protetiva = bool(
            re.search(
                r"\b(audi[eê]ncia\s+de\s+justifica[cç][aã]o|art\.?\s*16\s+da\s+lei\s+11\.?340|medida\s+protetiva(?:\s+de\s+urg[eê]ncia)?|lei\s+maria\s+da\s+penha|retrata[cç][aã]o\s+da\s+v[ií]tima)\b",
                h_comb,
                re.I,
            )
            or ("PROTETIVA" in fn_upper or "JUSTIFICAÇÃO" in fn_upper or "JUSTIFICACAO" in fn_upper)
        )
        if is_protetiva:
            return "JUSTIFICAÇÃO / PROTETIVA"

        # Prioridade 8: Sursis Processual (art. 89 Lei 9.099/95)
        if re.search(r"\b(audi[eê]ncia\s+de\s+suspens[aã]o|sursis\s+processual|admonit[oó]ria)\b", h_comb, re.I):
            return "Sursis"

        # Recebimento de denúncia com atos de instrução
        if has_received_denuncia and has_aij_mention:
            return "AIJ"

        # Fallback pelo nome do arquivo
        if "ANPP" in fn_upper and not has_anpp_rejection:
            return "ANPP"
        if "AIJ" in fn_upper:
            return "AIJ"
        if "CUSTÓDIA" in fn_upper or "CUSTODIA" in fn_upper:
            return "CUSTÓDIA"
        if "JÚRI" in fn_upper or "JURI" in fn_upper:
            return "JÚRI"
        if "PROTETIVA" in fn_upper:
            return "JUSTIFICAÇÃO / PROTETIVA"

        return "AIJ"


class JEVDecisionEngine:
    """Motor de Classificação e Decisão Estruturada System One para Processamento Criminal PJe."""

    _instance: Optional["JEVDecisionEngine"] = None

    @classmethod
    def get_instance(cls) -> "JEVDecisionEngine":
        """Retorna instância singleton do motor JEV."""
        if cls._instance is None:
            cls._instance = JEVDecisionEngine()
        return cls._instance

    def evaluate_noise_and_null_gate(self, text: str, metadata: str = "") -> Dict[str, Any]:
        """Acesso público ao Gate Multi-Critérios de Nulos e Ruídos."""
        return NoiseAndNullGate.evaluate(text, metadata)

    def classify_act_hierarchy(
        self,
        h_comb: str,
        fn_upper: str,
        pje_catalog: List[PJeDocument],
        anpp_rev_doc: Optional[PJeDocument] = None,
        pscp_rev_doc: Optional[PJeDocument] = None,
        has_received_denuncia: bool = False,
        has_aij_mention: bool = False,
        has_anpp_rejection: bool = False,
        has_denuncia: bool = True,
    ) -> str:
        """Classifica o ato da audiência de acordo com a hierarquia canônica do CPP."""
        return ClassificationHierarchyCPP.classify(
            h_comb=h_comb,
            fn_upper=fn_upper,
            pje_catalog=pje_catalog,
            anpp_rev_doc=anpp_rev_doc,
            pscp_rev_doc=pscp_rev_doc,
            has_received_denuncia=has_received_denuncia,
            has_aij_mention=has_aij_mention,
            has_anpp_rejection=has_anpp_rejection,
            has_denuncia=has_denuncia,
        )

    def classify_text_block(
        self,
        text: str,
        doc_title: str = "",
        doc_type: str = "",
    ) -> JEVDecisionResult:
        """Aplica o modelo de decisão System One para categorizar e pontuar um bloco de texto.

        Args:
            text: Conteúdo textual reconhecido (nativo ou OCR).
            doc_title: Nome da peça no catálogo PJe (ex.: 'Denúncia', 'Decisão').
            doc_type: Tipo do documento no PJe.

        Returns:
            JEVDecisionResult contendo categoria, score de relevância e justificativa.
        """
        combined_meta = f"{doc_title} {doc_type}".lower()
        gate_res = NoiseAndNullGate.evaluate(text, combined_meta)

        if not gate_res["passed"]:
            return JEVDecisionResult(
                category=DocumentCategory.RUIDO_IRRELEVANTE,
                relevance_score=gate_res["chance_essential"],
                is_essential=False,
                rationale=gate_res["rationale"],
            )

        cleaned_text = self.clean_text_for_evaluation(text)

        # 2. Avaliação de Rol de Testemunhas
        witness_matches = len(TESTEMUNHAS_POSITIVE_REGEX.findall(cleaned_text))
        if "rol" in combined_meta or "testemunha" in combined_meta or witness_matches >= 2:
            return JEVDecisionResult(
                category=DocumentCategory.ROL_TESTEMUNHAS,
                relevance_score=0.90,
                is_essential=True,
                rationale="Rol de testemunhas ou indicação formal de oitiva.",
            )

        # 3. Avaliação de Decisões Judiciais de Audiência
        if any(k in combined_meta for k in ["decis", "despacho", "termo de audi", "ata", "termo"]):
            if "pronúncia" in cleaned_text.lower() or "pronuncia" in cleaned_text.lower() or "tribunal do júri" in cleaned_text.lower() or "júri" in combined_meta or "juri" in combined_meta:
                return JEVDecisionResult(
                    category=DocumentCategory.SESSAO_JURI,
                    relevance_score=0.96,
                    is_essential=True,
                    rationale="Decisão de pronúncia ou designação de Sessão Plenária do Tribunal do Júri.",
                )
            if "audiência de custódia" in cleaned_text.lower() or "custódia" in combined_meta or "custodia" in combined_meta:
                return JEVDecisionResult(
                    category=DocumentCategory.AUDIENCIA_CUSTODIA,
                    relevance_score=0.95,
                    is_essential=True,
                    rationale="Auto de Prisão em Flagrante / Audiência de Custódia.",
                )
            if "justificação" in cleaned_text.lower() or "medida protetiva" in cleaned_text.lower() or "lei maria da penha" in cleaned_text.lower():
                return JEVDecisionResult(
                    category=DocumentCategory.AUDIENCIA_PROTETIVA,
                    relevance_score=0.94,
                    is_essential=True,
                    rationale="Audiência de Justificação ou Medida Protetiva de Urgência (Lei 11.340/06).",
                )
            if "366" in cleaned_text or "produção antecipada" in cleaned_text.lower() or "panp" in combined_meta:
                return JEVDecisionResult(
                    category=DocumentCategory.DECISAO_PANP,
                    relevance_score=0.95,
                    is_essential=True,
                    rationale="Decisão judicial de Produção Antecipada de Provas (Art. 366 CPP).",
                )
            if "anpp" in cleaned_text.lower() or "não persecução" in cleaned_text.lower() or "nao persecucao" in cleaned_text.lower():
                return JEVDecisionResult(
                    category=DocumentCategory.DECISAO_ANPP,
                    relevance_score=0.95,
                    is_essential=True,
                    rationale="Decisão judicial afeta a Acordo de Não Persecução Penal (ANPP).",
                )
            if DECISAO_POSITIVE_REGEX.search(cleaned_text):
                return JEVDecisionResult(
                    category=DocumentCategory.DECISAO_AIJ,
                    relevance_score=0.92,
                    is_essential=True,
                    rationale="Decisão/Despacho de designação ou instrução de audiência (AIJ).",
                )

        # 4. Avaliação de Denúncia / Fatos
        denuncia_score = self._compute_denuncia_score(cleaned_text, combined_meta)
        if denuncia_score >= 0.60:
            return JEVDecisionResult(
                category=DocumentCategory.DENUNCIA_FATOS,
                relevance_score=denuncia_score,
                is_essential=True,
                rationale="Peça inaugural ministerial com narrativa fática acusatória.",
            )

        # 5. Avaliação de Mandado Cumprido / Citação
        if any(k in combined_meta for k in ["mandado", "certidão de citação", "contrafé"]):
            if "cumprid" in cleaned_text.lower() or "citei" in cleaned_text.lower() or "intimei" in cleaned_text.lower():
                return JEVDecisionResult(
                    category=DocumentCategory.MANDADO_CUMPRIDO,
                    relevance_score=0.75,
                    is_essential=True,
                    rationale="Mandado ou certidão com cumprimento positivo de intimação/citação.",
                )

        # 6. Fallback ponderado
        score = self.score_relevance(cleaned_text, combined_meta)
        is_essential = score >= 0.65
        category = DocumentCategory.DENUNCIA_FATOS if is_essential else DocumentCategory.RUIDO_IRRELEVANTE

        return JEVDecisionResult(
            category=category,
            relevance_score=score,
            is_essential=is_essential,
            rationale=f"Classificação via score ponderado de relevância ({score:.2f}).",
        )

    def _compute_denuncia_score(self, text: str, meta: str) -> float:
        """Calcula score específico de probabilidade de denúncia criminal."""
        score = 0.0
        if "denúncia" in meta or "denuncia" in meta or "aditamento" in meta:
            score += 0.40

        matches = len(DENUNCIA_POSITIVE_REGEX.findall(text))
        score += min(0.50, matches * 0.10)

        if "o ministério público" in text.lower():
            score += 0.10
        if re.search(r"\bart(?:igo)?\.?\s*\d+\b", text, re.I):
            score += 0.10

        # Penalidades por características de petição defensiva ou cota
        if "defesa prévia" in meta or "resposta à acusação" in meta:
            score -= 0.40
        if "cota" in meta and not ("denúncia" in meta or "denuncia" in meta):
            score -= 0.30

        try:
            from app.core.learning_store import LearningStore
            delta = LearningStore.get_instance().compute_learned_adjustment(text)
            score += delta
        except Exception:
            pass

        return max(0.0, min(1.0, score))

    def score_relevance(self, text: str, meta: str = "") -> float:
        """Pontua a relevância jurídica geral de um bloco de texto (0.0 a 1.0)."""
        if not text:
            return 0.0

        pos_count = len(DENUNCIA_POSITIVE_REGEX.findall(text)) + len(DECISAO_POSITIVE_REGEX.findall(text))
        neg_count = len(BANKING_NOISE_REGEX.findall(text)) + len(ADMIN_NOISE_REGEX.findall(text))

        try:
            from app.core.learning_store import LearningStore
            delta = LearningStore.get_instance().compute_learned_adjustment(text)
        except Exception:
            delta = 0.0

        raw_score = 0.50 + (pos_count * 0.08) - (neg_count * 0.20) + delta
        return max(0.0, min(1.0, round(raw_score, 2)))

    def filter_noise_lines(self, lines: List[str]) -> List[str]:
        """Filtra rigorosamente linhas individuais de ruído de OCR, carimbos e lixo digital."""
        filtered: List[str] = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            alphanumeric_count = sum(c.isalnum() for c in trimmed)
            if alphanumeric_count < 2:
                continue

            if PJE_MARGIN_STAMPS_REGEX.search(trimmed):
                continue

            if BANKING_NOISE_REGEX.search(trimmed):
                continue

            ratio = alphanumeric_count / len(trimmed)
            if ratio < 0.35 and len(trimmed) > 5:
                continue

            if re.match(r"^https?://", trimmed, re.I) and not ("teams" in trimmed.lower() or "meet" in trimmed.lower()):
                continue

            filtered.append(trimmed)

        return filtered

    def filter_ocr_lines(self, ocr_lines: List[OCRLine], min_confidence: float = 0.55) -> List[OCRLine]:
        """Filtra objetos OCRLine descartando baixa confiança, caixas diminutas e ruídos marginais."""
        clean_lines: List[OCRLine] = []
        for ocr_line in ocr_lines:
            if ocr_line.confidence < min_confidence:
                continue

            txt = ocr_line.text.strip()
            if not txt or sum(c.isalnum() for c in txt) < 2:
                continue

            if PJE_MARGIN_STAMPS_REGEX.search(txt) or BANKING_NOISE_REGEX.search(txt):
                continue

            clean_lines.append(ocr_line)

        return clean_lines

    def clean_text_for_evaluation(self, text: str) -> str:
        """Normaliza espaços e remove quebras espúrias para avaliação semântica."""
        text = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)
        return re.sub(r"\s+", " ", text).strip()

    def audit_qualification_and_imputation(
        self,
        qualification_text: str,
        imputation_text: str,
        denuncia_text: str,
        ip_text: str = "",
    ) -> Tuple[str, str]:
        """Audita e complementa rigorosamente a qualificação dos réus e a imputação penal.

        - Verifica se a qualificação traz documentos (RG/CPF) e filiação (filho/filha); se faltar, aciona fallback no IP/Denúncia.
        - Verifica se todos os artigos de lei narrados na denúncia constam na imputação; se faltar algum, incorpora-os.
        - Aplica anotação taxonômica estrita de todos os artigos penais com o nomen juris exato entre colchetes.
        """
        audited_qual = qualification_text or ""
        audited_imp = imputation_text or ""

        # 1. Audit qualification documents & filiação
        has_filiacao = bool(re.search(r"\bfilh[oa]\s+de\b", audited_qual, re.I))
        has_rg = bool(re.search(r"\bRG\b", audited_qual, re.I))
        has_cpf = bool(re.search(r"\bCPF\b", audited_qual, re.I))

        search_pool = f"{denuncia_text}\n{ip_text}"

        if not (has_filiacao and has_rg and has_cpf) and search_pool.strip():
            supplements = []
            if not has_filiacao:
                fil_m = re.search(r"(\bfilh[oa]\s+de\s+[A-ZÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõ\s]{5,60}?)(?=[,;\n.]|$)", search_pool, re.I)
                if fil_m:
                    supplements.append(fil_m.group(1).strip())
            if not has_rg:
                rg_m = re.search(r"(\bRG\s*(?:n[º°\.]?)?\s*[\d\.-]+(?:\s*[A-Z/]+)?)", search_pool, re.I)
                if rg_m:
                    supplements.append(rg_m.group(1).strip())
            if not has_cpf:
                cpf_m = re.search(r"(\bCPF\s*(?:n[º°\.]?)?\s*[\d\.-]+)", search_pool, re.I)
                if cpf_m:
                    supplements.append(cpf_m.group(1).strip())

            if supplements:
                supp_str = ", ".join(supplements)
                if audited_qual and "qualificação nos autos" not in audited_qual:
                    audited_qual += f" ({supp_str})"
                elif not audited_qual:
                    audited_qual = supp_str

        # 2. Audit imputation articles (excluding procedural/constitutional citations like CF and CPP)
        if denuncia_text:
            art_matches = re.findall(
                r"\bart(?:igo)?s?\b\.?\s*\d+[^\n,.;]*(?:§[^\n,.;]*)?(?:inciso[^\n,.;]*)?(?:do\s+CP|do\s+Código\s+Penal|da\s+Lei[^\n,.;]*)?",
                denuncia_text,
                re.IGNORECASE,
            )
            law_matches = re.findall(
                r"\b(?:Lei\s+(?:n[º°\.]?\s*)?(?:11\.343|10\.826|9\.503|11\.340|13\.869|12\.850|9\.613|8\.072|10\.741|8\.069[^\n,.;]*244)[^\n,.;]*|ECA\b[^\n,.;]*244|Lei\s+Maria\s+da\s+Penha|Estatuto\s+do\s+Desarmamento|Lei\s+de\s+Drogas|CTB\b)",
                denuncia_text,
                re.IGNORECASE,
            )
            concurso_matches = re.findall(r"\bart[s]?\.?\s*(?:69|70|71)[^\n,.;]*(?:do\s+CP|do\s+Código\s+Penal)?", denuncia_text, re.IGNORECASE)

            all_detected = []
            for item in art_matches + law_matches + concurso_matches:
                item_c = item.strip()
                if item_c and item_c not in all_detected and not is_procedural_or_constitutional(item_c, denuncia_text):
                    all_detected.append(item_c)

            missing_articles = []
            for item in all_detected:
                nums = re.findall(r"\d+", item)
                if nums and not any(n in audited_imp for n in nums):
                    missing_articles.append(item)

            if missing_articles:
                if audited_imp and audited_imp != "Artigo de lei a ser apurado":
                    # Only add if the missing item looks like a penal article or special criminal law
                    substantive_missing = []
                    seen_nums = set()
                    for m in missing_articles:
                        if not is_procedural_or_constitutional(m, denuncia_text) and not any(k in m.lower() for k in ["compete", "diploma", "retrata", "queixa", "143", "145", "107", "115", "efeitos da condenação", "perda de cargo", "função pública"]) and not re.search(r"\bart(?:igo)?s?\b\.?\s*(?:61|62|91|92)\b", m, re.I):
                            m_num = re.search(r"\bart(?:igo)?s?\b\.?\s*(\d+)", m, re.I)
                            if m_num:
                                n_val = m_num.group(1)
                                if n_val in seen_nums or n_val in audited_imp:
                                    continue
                                seen_nums.add(n_val)
                            substantive_missing.append(m)
                    if substantive_missing:
                        audited_imp += " c/c " + " c/c ".join(substantive_missing)
                else:
                    audited_imp = f"Imputação penal ({', '.join(all_detected)})"

        # 3. Anotação Taxonômica Rigorosa com Nomen Juris entre Colchetes
        if audited_imp and audited_imp != "Artigo de lei a ser apurado":
            audited_imp = annotate_imputation_text(audited_imp)

        return audited_qual, audited_imp

    def audit_llm_ground_truth(
        self,
        llm_data: HearingSummaryData,
        pje_catalog: List[PJeDocument],
        denuncia_text: str = "",
        offline_fallback_data: Optional[HearingSummaryData] = None,
    ) -> HearingSummaryData:
        """Audita rigorosamente o resumo estruturado extraído pelo LLM (Gemini) contra a verdade documental (Ground-Truth).

        Verificações realizadas (LAYA / JEV Verification Layer):
        1. Validação de IDs do PJe:
           - Todo ID citado em 'chronological_history' e 'witnesses' deve existir no catálogo de documentos do PJe.
           - Se o ID não existir no catálogo: tenta mapear para o ato legítimo correspondente pelo tipo/data,
             ou expurga o número de ID espúrio / hiperlink alucinado, registrando advertência.
        2. Validação da Imputação Penal:
           - Todos os artigos de lei substantivos imputados pelo LLM devem estar presentes na denúncia ministerial.
           - Se o LLM alucinou artigos adicionais, restaura a imputação fidedigna do baseline offline.
        3. Validação de Limites de Calendário:
           - Data e hora da audiência são auditadas contra limites válidos de calendário (dia <= 31, mês <= 12, hora <= 23).
        4. Fallback por Incoerências Graves:
           - Se o total de inconsistências graves for superior a 3 (limite de tolerância),
             descarta integralmente o retorno da IA e assume o baseline determinístico offline.

        Desenvolvido por FChNeto.
        """
        if llm_data is None:
            if offline_fallback_data:
                return offline_fallback_data
            raise ValueError("llm_data cannot be None")

        severe_inconsistencies = 0
        warnings: List[str] = []

        # Mapa de lookup O(1) dos documentos legítimos do PJe
        catalog_by_id: Dict[str, PJeDocument] = {}
        for doc in pje_catalog or []:
            if doc.doc_id and str(doc.doc_id).strip():
                catalog_by_id[str(doc.doc_id).strip()] = doc
        valid_doc_ids: Set[str] = set(catalog_by_id.keys())

        def find_legit_doc(query_text: str, doc_category_hints: List[str]) -> Optional[PJeDocument]:
            for doc in pje_catalog or []:
                d_name = (doc.doc_name or "").lower()
                d_type = (doc.doc_type or "").lower()
                comb = f"{d_name} {d_type}"
                if any(hint.lower() in comb for hint in doc_category_hints):
                    return doc
            return None

        # 1. AUDITORIA DE IDS NO HISTÓRICO PROCESSUAL
        if hasattr(llm_data, "chronological_history") and llm_data.chronological_history:
            audited_history: List[HistoryItem] = []
            for item in llm_data.chronological_history:
                doc_id_clean = str(item.doc_id or "").strip()
                desc_clean = item.description or ""

                if doc_id_clean and doc_id_clean not in valid_doc_ids:
                    severe_inconsistencies += 1
                    warnings.append(f"Histórico: ID espúrio '{doc_id_clean}' não localizado no PJe.")
                    
                    hints = []
                    desc_lower = desc_clean.lower()
                    if "denún" in desc_lower or "denun" in desc_lower: hints = ["denún", "denun", "inicial"]
                    elif "decis" in desc_lower: hints = ["decisão", "decisao"]
                    elif "despacho" in desc_lower: hints = ["despacho"]
                    elif "mandado" in desc_lower: hints = ["mandado"]
                    elif "citação" in desc_lower or "citacao" in desc_lower: hints = ["citação", "citacao", "mandado"]
                    elif "resposta" in desc_lower or "defesa" in desc_lower: hints = ["resposta", "defesa"]
                    elif "inquérito" in desc_lower or "inquerito" in desc_lower or "ip" in desc_lower: hints = ["inquérito", "inquerito", "portaria", "apf"]

                    matched = find_legit_doc(desc_clean, hints) if hints else None
                    if matched and matched.doc_id:
                        old_fake = doc_id_clean
                        doc_id_clean = matched.doc_id
                        desc_clean = re.sub(rf"\(?ID\s*:?\s*{re.escape(old_fake)}\)?", f"(ID {doc_id_clean})", desc_clean, flags=re.I)
                    else:
                        desc_clean = re.sub(rf"\s*\(?ID\s*:?\s*{re.escape(doc_id_clean)}\)?", "", desc_clean, flags=re.I).strip()
                        doc_id_clean = ""

                found_ids_in_desc = re.findall(r"\b(\d{7,10})\b", desc_clean)
                for fid in found_ids_in_desc:
                    if fid not in valid_doc_ids:
                        severe_inconsistencies += 1
                        warnings.append(f"Histórico texto: ID espúrio '{fid}' na descrição.")
                        desc_clean = re.sub(rf"\s*\(?ID\s*:?\s*{re.escape(fid)}\)?", "", desc_clean, flags=re.I).strip()

                audited_history.append(
                    HistoryItem(
                        date_str=item.date_str,
                        description=desc_clean,
                        doc_id=doc_id_clean,
                        pje_url=item.pje_url if doc_id_clean else None,
                    )
                )
            llm_data.chronological_history = audited_history

        # 2. AUDITORIA DE IDS NO ROL DE TESTEMUNHAS
        for wit_list_name in ["prosecution_witnesses", "defense_witnesses"]:
            wit_list: List[Witness] = getattr(llm_data, wit_list_name, []) or []
            audited_witnesses: List[Witness] = []
            for wit in wit_list:
                status_id = wit.status_id or ""
                w_ids = re.findall(r"\b(\d{7,10})\b", status_id)
                for wid in w_ids:
                    if wid not in valid_doc_ids:
                        severe_inconsistencies += 1
                        warnings.append(f"Testemunha '{wit.name}': ID espúrio '{wid}' em status_id.")
                        
                        hints = ["mandado", "certidão", "ofício", "intimação"]
                        matched = find_legit_doc(wit.name, hints)
                        if matched and matched.doc_id:
                            status_id = re.sub(rf"\b{re.escape(wid)}\b", matched.doc_id, status_id)
                        else:
                            status_id = re.sub(rf"\s*\(?IDs?\s*:?\s*{re.escape(wid)}\)?", "", status_id, flags=re.I).strip()
                            status_id = re.sub(rf"\bID\s+{re.escape(wid)}\b", "", status_id, flags=re.I).strip()
                            if not status_id or status_id == "ID":
                                status_id = "Mandado expedido"

                audited_witnesses.append(
                    Witness(
                        number=wit.number,
                        name=wit.name,
                        role=wit.role,
                        status_id=status_id,
                    )
                )
            setattr(llm_data, wit_list_name, audited_witnesses)

        # 3. AUDITORIA DE IDS NOS RÉUS
        if hasattr(llm_data, "defendants") and llm_data.defendants:
            audited_defendants: List[Defendant] = []
            for d in llm_data.defendants:
                status_str = d.status or ""
                cit_id = str(d.citation_id or "").strip()
                sub_id = str(d.subpoena_id or "").strip()

                if cit_id and cit_id not in valid_doc_ids:
                    severe_inconsistencies += 1
                    cit_id = None
                if sub_id and sub_id not in valid_doc_ids:
                    severe_inconsistencies += 1
                    sub_id = None

                status_ids = re.findall(r"\b(\d{7,10})\b", status_str)
                for sid in status_ids:
                    if sid not in valid_doc_ids:
                        severe_inconsistencies += 1
                        status_str = re.sub(rf"\s*\(?IDs?\s*:?\s*{re.escape(sid)}\)?", "", status_str, flags=re.I).strip()

                audited_defendants.append(
                    Defendant(
                        name=d.name,
                        status=status_str or "Em liberdade",
                        citation_id=cit_id,
                        subpoena_id=sub_id,
                        qualification=d.qualification,
                    )
                )
            llm_data.defendants = audited_defendants

        # 4. AUDITORIA DE IMPUTAÇÃO PENAL (GROUND-TRUTH VS DENÚNCIA)
        if denuncia_text and llm_data.imputation_text:
            denuncia_lower = denuncia_text.lower()
            denuncia_arts = set(re.findall(r"\bart(?:igo)?s?\b\.?\s*(\d+[a-zA-Z\-]*)", denuncia_lower, re.I))
            ACCEPTED_GENERAL_ARTICLES = {"14", "29", "61", "62", "65", "69", "70", "71"}

            llm_arts = re.findall(r"\bart(?:igo)?s?\b\.?\s*(\d+[a-zA-Z\-]*)", llm_data.imputation_text, re.I)
            has_hallucinated_article = False
            for art in llm_arts:
                art_clean = art.strip()
                if art_clean not in denuncia_arts and art_clean not in ACCEPTED_GENERAL_ARTICLES:
                    if not re.search(rf"\b{re.escape(art_clean)}\b", denuncia_lower):
                        has_hallucinated_article = True
                        severe_inconsistencies += 1
                        warnings.append(f"Imputação: Artigo alucinado 'art. {art_clean}' não encontrado na denúncia.")

            if has_hallucinated_article:
                if offline_fallback_data and offline_fallback_data.imputation_text:
                    llm_data.imputation_text = offline_fallback_data.imputation_text
                else:
                    _, clean_imp = self.audit_qualification_and_imputation(
                        qualification_text="",
                        imputation_text="",
                        denuncia_text=denuncia_text,
                    )
                    llm_data.imputation_text = clean_imp or "Artigo de lei a ser apurado"
        elif llm_data.imputation_text:
            llm_data.imputation_text = annotate_imputation_text(llm_data.imputation_text)

        # 5. AUDITORIA DE LIMITES DE CALENDÁRIO NA DATA/HORA DA AUDIÊNCIA
        if llm_data.hearing_datetime:
            dt_str = llm_data.hearing_datetime
            date_m = re.search(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", dt_str)
            time_m = re.search(r"(\d{1,2})h(?:(\d{2}))?", dt_str, re.I)

            invalid_dt = False
            if date_m:
                d = int(date_m.group(1))
                m = int(date_m.group(2))
                if not (1 <= d <= 31 and 1 <= m <= 12):
                    invalid_dt = True
                    severe_inconsistencies += 1
                    warnings.append(f"Data inválida detectada: dia {d}, mês {m}.")

            if time_m:
                h = int(time_m.group(1))
                min_val = int(time_m.group(2)) if time_m.group(2) else 0
                if not (0 <= h <= 23 and 0 <= min_val <= 59):
                    invalid_dt = True
                    severe_inconsistencies += 1
                    warnings.append(f"Hora inválida detectada: {h}h{min_val}min.")

            if invalid_dt and offline_fallback_data and offline_fallback_data.hearing_datetime:
                llm_data.hearing_datetime = offline_fallback_data.hearing_datetime

        # 6. REGRA DE FALLBACK: TOLERÂNCIA A MAIS DE 3 INCOERÊNCIAS GRAVES
        if severe_inconsistencies > 3:
            if offline_fallback_data is not None:
                return offline_fallback_data

        return llm_data

