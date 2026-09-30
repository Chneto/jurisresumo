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
from app.core.models import DocumentCategory, JEVDecisionResult, OCRLine, PJeDocument


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

# Positive signals for Audiência Decisions (AIJ, ANPP, PAnP)
DECISAO_POSITIVE_REGEX = re.compile(
    r"(?:"
    r"design[ao]\s+o\s+dia\s+\d{1,2}|"
    r"audi[eê]ncia\s+de\s+instru[cç][aã]o\s+e\s+julgamento|"
    r"audi[eê]ncia\s+de\s+homologa[cç][aã]o|"
    r"acordo\s+de\s+n[aã]o\s+persecu[cç][aã]o\s+penal|"
    r"produ[cç][aã]o\s+antecipada\s+de\s+provas|"
    r"art\.?\s*366\s+do\s+cpp|"
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
    comb = f"{match_text} {context_text}".lower()
    if re.search(r"\b(?:da\s+cf(?:/88)?|da\s+constitui[cç][aã]o|do\s+cpp|do\s+c[oó]digo\s+de\s+processo\s+penal|processual\s+penal|processo\s+penal)\b", comb):
        return True
    if re.search(r"\bart(?:igo)?s?\b\.?\s*(?:41|396(?:-[a-z])?|399|400|383|384)\b", match_text, re.I):
        if not re.search(r"\b(?:do\s+cp|do\s+c[oó]digo\s+penal)\b", comb):
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
        pje_catalog: List[PJeDocument],
        anpp_rev_doc: Optional[PJeDocument] = None,
        pscp_rev_doc: Optional[PJeDocument] = None,
        has_received_denuncia: bool = False,
        has_aij_mention: bool = False,
        has_anpp_rejection: bool = False,
        has_denuncia: bool = True,
    ) -> str:
        """Determina o tipo de ato da audiência segundo as prioridades do CPP.

        Hierarquia:
        1. Revogação de ANPP ou PSCP -> AIJ (retomada da marcha penal)
        2. PAnP (art. 366 CPP) -> PAnP
        3. ANPP (art. 28-A CPP) -> ANPP (se não houver revogação nem rejeição)
        4. AIJ (Instrução e Julgamento) -> AIJ
        5. Custódia (APF sem denúncia) -> Custódia
        6. Sursis Processual (art. 89 Lei 9.099/95) -> Sursis
        """
        # Prioridade 1: Revogação de ANPP ou PSCP impõe obrigatoriamente AIJ
        if anpp_rev_doc or pscp_rev_doc:
            return "AIJ"

        # Prioridade 2: PAnP (Art. 366 CPP)
        if re.search(r"\b(produ[cç][aã]o\s+antecipada|panp|art\.?\s*366)\b", h_comb, re.I) or "PANP" in fn_upper:
            return "PAnP"

        # Prioridade 3: ANPP homologatório em designação afirmativa
        is_anpp_in_hearing = bool(
            re.search(
                r"(?:homologa[cç][aã]o\s+d[eo]\s+(?:acordo(?:\s+de\s+n[aã]o\s+persecu[cç][aã]o(?:\s+penal)?)?|anpp)|audi[eê]ncia\s+(?:de\s+anpp|para\s+fins\s+do\s+art\.?\s*28-a|para\s+homologa[cç][aã]o\s+d[eo]\s+acordo))",
                h_comb,
                re.I,
            )
        )
        if is_anpp_in_hearing and not has_anpp_rejection:
            return "ANPP"

        # Prioridade 4: AIJ explícita
        if re.search(r"\b(instru[cç][aã]o(?:\s+e\s+julgamento)?|aij|oitiva\s+d[ae]s?\s+testemunhas?|inquirir\s+testemunhas?|interrogat[oó]rio)\b", h_comb, re.I):
            return "AIJ"

        # Prioridade 5: Custódia (sem denúncia)
        if re.search(r"\b(audi[eê]ncia\s+de\s+cust[oó]dia|termo\s+de\s+audi[eê]ncia\s+de\s+cust[oó]dia)\b", h_comb, re.I) and not has_denuncia:
            return "Custódia"

        # Prioridade 6: Sursis
        if re.search(r"\b(audi[eê]ncia\s+de\s+suspens[aã]o|sursis\s+processual|admonit[oó]ria)\b", h_comb, re.I):
            return "Sursis"

        # Prioridade 7: Recebimento de denúncia com atos de instrução
        if has_received_denuncia and has_aij_mention:
            return "AIJ"

        # Fallback pelo nome do arquivo
        if "ANPP" in fn_upper and not has_anpp_rejection:
            return "ANPP"
        if "AIJ" in fn_upper:
            return "AIJ"

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
        if any(k in combined_meta for k in ["decis", "despacho", "termo de audi", "ata"]):
            if "366" in cleaned_text or "produção antecipada" in cleaned_text or "panp" in combined_meta:
                return JEVDecisionResult(
                    category=DocumentCategory.DECISAO_PANP,
                    relevance_score=0.95,
                    is_essential=True,
                    rationale="Decisão judicial de Produção Antecipada de Provas (Art. 366 CPP).",
                )
            if "anpp" in cleaned_text or "não persecução" in cleaned_text:
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
            law_matches = re.findall(r"\bLei\s+(?:n[º°\.]?\s*)?[\d\./]+[^\n,.;]*", denuncia_text, re.IGNORECASE)
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
                    audited_imp += " c/c " + " c/c ".join(missing_articles)
                else:
                    audited_imp = f"Imputação penal ({', '.join(all_detected)})"

        # 3. Anotação Taxonômica Rigorosa com Nomen Juris entre Colchetes
        if audited_imp and audited_imp != "Artigo de lei a ser apurado":
            audited_imp = annotate_imputation_text(audited_imp)

        return audited_qual, audited_imp
