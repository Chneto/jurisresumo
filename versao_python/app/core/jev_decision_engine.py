"""Motor de Decisão Estruturada JEV (System One) e Roteamento Jurídico Leya.

Implementa um classificador determinístico e probabilístico de alto desempenho (System One),
sem dependências externas de rede, para aferição de relevância, descarte rigoroso de ruídos de OCR
(carimbos, comprovantes bancários, certidões avulsas) e roteamento de peças essenciais
(Denúncia/Fatos, Decisões de Audiência, Qualificação e Testemunhas).

Inspirado nos conceitos de TypeSafe Jev (decisão estruturada e tipada) e Leya (precisão de
fluxos jurídicos e ground-truth documental).

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Optional, Set, Tuple

from app.core.models import DocumentCategory, JEVDecisionResult, OCRLine


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


class JEVDecisionEngine:
    """Motor de Classificação e Decisão Estruturada System One para Processamento Criminal PJe."""

    _instance: Optional["JEVDecisionEngine"] = None

    @classmethod
    def get_instance(cls) -> "JEVDecisionEngine":
        """Retorna instância singleton do motor JEV."""
        if cls._instance is None:
            cls._instance = JEVDecisionEngine()
        return cls._instance

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
        if not text or not text.strip():
            return JEVDecisionResult(
                category=DocumentCategory.RUIDO_IRRELEVANTE,
                relevance_score=0.0,
                is_essential=False,
                rationale="Bloco de texto vazio ou nulo.",
            )

        combined_meta = f"{doc_title} {doc_type}".lower()
        cleaned_text = self.clean_text_for_evaluation(text)

        # 1. Checagem imediata de ruído financeiro / bancário / administrativo (System One fast-path)
        if BANKING_NOISE_REGEX.search(cleaned_text) or BANKING_NOISE_REGEX.search(combined_meta):
            return JEVDecisionResult(
                category=DocumentCategory.RUIDO_IRRELEVANTE,
                relevance_score=0.05,
                is_essential=False,
                rationale="Identificado comprovante bancário, guia de custas ou extrato financeiro irrelevante.",
            )

        if ADMIN_NOISE_REGEX.search(cleaned_text) and not DENUNCIA_POSITIVE_REGEX.search(cleaned_text):
            return JEVDecisionResult(
                category=DocumentCategory.RUIDO_IRRELEVANTE,
                relevance_score=0.15,
                is_essential=False,
                rationale="Certidão puramente administrativa de trâmite/juntada sem teor fático.",
            )

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

        # Ajuste adaptativo do LearningStore (aprendizado contínuo offline)
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

        # Ajuste adaptativo do LearningStore (aprendizado contínuo offline)
        try:
            from app.core.learning_store import LearningStore
            delta = LearningStore.get_instance().compute_learned_adjustment(text)
        except Exception:
            delta = 0.0

        raw_score = 0.50 + (pos_count * 0.08) - (neg_count * 0.20) + delta
        return max(0.0, min(1.0, round(raw_score, 2)))

    def filter_noise_lines(self, lines: List[str]) -> List[str]:
        """Filtra rigorosamente linhas individuais de ruído de OCR, carimbos e lixo digital.

        Args:
            lines: Lista de linhas de texto extraídas.

        Returns:
            Lista de linhas úteis limpas.
        """
        filtered: List[str] = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Elimina linhas muito curtas sem caracteres alfanuméricos úteis (ex: '.', '-', '--', '~', '||')
            alphanumeric_count = sum(c.isalnum() for c in trimmed)
            if alphanumeric_count < 2:
                continue

            # Elimina carimbos de margem do PJe
            if PJE_MARGIN_STAMPS_REGEX.search(trimmed):
                continue

            # Elimina códigos de barras ou comprovantes de autenticação mecânica
            if BANKING_NOISE_REGEX.search(trimmed):
                continue

            # Elimina linhas compostas quase que exclusivamente por pontuação de OCR danificado
            ratio = alphanumeric_count / len(trimmed)
            if ratio < 0.35 and len(trimmed) > 5:
                continue

            # Elimina links avulsos que não sejam de videoconferência (Teams/Meet)
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
        # Unir palavras com hífen quebrado na quebra de linha (ex: de-\n signou -> designou)
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
        """
        audited_qual = qualification_text or ""
        audited_imp = imputation_text or ""

        # 1. Audit qualification documents & filiação
        has_filiacao = bool(re.search(r"\bfilh[oa]\b|\bm[aã]e\b|\bpai\b|\bgenitor", audited_qual, re.I))
        has_rg = bool(re.search(r"\bRG\b|\b\d{6,}\b", audited_qual, re.I))
        has_cpf = bool(re.search(r"\bCPF\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", audited_qual, re.I))

        search_pool = f"{denuncia_text}\n{ip_text}"

        if not (has_filiacao and has_rg and has_cpf) and search_pool.strip():
            supplements = []
            if not has_filiacao:
                fil_m = re.search(r"(\bfilh[oa]\s+de\s+[A-ZÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõ\s]{3,100}?)(?=[,;\n.]|$)", search_pool, re.I)
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

        # 2. Audit imputation articles
        if denuncia_text:
            penal_rx = re.compile(
                r"\bart(?:igo)?s?\b\.?\s*\d+(?:-[A-Z])?\b"
                r"(?:\s*,\s*§\s*\d+[º°]?(?:-[A-Z])?|\s+§\s*\d+[º°]?(?:-[A-Z])?)*"
                r"(?:\s*,\s*(?:inciso\s+)?[I|V|X|L|C|D|M]+\b|\s+(?:inciso\s+)?[I|V|X|L|C|D|M]+\b)*"
                r"(?:\s*,\s*al[íi]nea\s+[a-z]|\s+al[íi]nea\s+[a-z])*"
                r"(?:\s+(?:c/c|comb|combinado\s+com)\s+art(?:igo)?s?\b\.?\s*\d+[^,.;\n]*)*"
                r"(?:\s+(?:do\s+CP|do\s+C[oó]digo\s+Penal|da\s+Lei[^\n,.;]*))?",
                re.IGNORECASE,
            )
            art_matches = [a.strip(" ,.;") for a in penal_rx.findall(denuncia_text) if a.strip(" ,.;")]

            law_rx = re.compile(
                r"\b(?:Lei\s+(?:n[º°\.]?\s*)?[\d\./]+|ECA|Lei\s+Maria\s+da\s+Penha|Estatuto\s+do\s+Desarmamento|Lei\s+de\s+Drogas)"
                r"(?:\s*\([^\)]+\))?(?:\s*,\s*art(?:igo)?\.?\s*\d+[^;.\n]*)?",
                re.IGNORECASE,
            )
            law_matches = [l.strip(" ,.;") for l in law_rx.findall(denuncia_text) if l.strip(" ,.;")]

            concurso_rx = re.compile(
                r"\bart[s]?\.?\s*(?:69|70|71)[^\n,.;]*(?:do\s+CP|do\s+C[oó]digo\s+Penal)?",
                re.IGNORECASE,
            )
            concurso_matches = [c.strip(" ,.;") for c in concurso_rx.findall(denuncia_text) if c.strip(" ,.;")]

            all_detected = []
            for item in art_matches + law_matches + concurso_matches:
                if item and item not in all_detected:
                    all_detected.append(item)

            missing_articles = []
            for item in all_detected:
                nums = re.findall(r"\d+", item)
                if nums:
                    num_found = any(n in audited_imp for n in nums)
                    has_paragraph_in_item = "§" in item
                    has_paragraph_in_imp = "§" in audited_imp
                    has_eca_in_item = "244" in item or "ECA" in item
                    has_eca_in_imp = "244" in audited_imp or "ECA" in audited_imp

                    if not num_found or (has_paragraph_in_item and not has_paragraph_in_imp) or (has_eca_in_item and not has_eca_in_imp):
                        if item not in audited_imp:
                            missing_articles.append(item)

            if missing_articles:
                if audited_imp and audited_imp != "Artigo de lei a ser apurado":
                    audited_imp += " c/c " + " c/c ".join(missing_articles)
                else:
                    audited_imp = f"Imputação penal ({', '.join(all_detected)})"

        return audited_qual, audited_imp

