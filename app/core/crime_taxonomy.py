"""Taxonomia Penal Canônica do JURISRESUMO.

Mapeia e anota artigos da imputação penal com o nomen juris exato entre colchetes.
Exemplos:
- Art. 155 [furto]
- Art. 155, § 4º, I e IV [furto qualificado]
- Art. 157, § 2º, II [roubo majorado]
- Art. 157, § 3º, II [latrocínio]
- Art. 121 [homicídio]
- Art. 121, § 2º, I e IV [homicídio qualificado]
- Art. 33, caput [tráfico de drogas] da Lei 11.343/06
- Art. 35 [associação para o tráfico]
- Art. 12 [posse irregular de arma de fogo de uso permitido] da Lei 10.826/03
- Art. 14 [porte ilegal de arma de fogo de uso permitido] da Lei 10.826/03
- Art. 16 [posse ou porte ilegal de arma de fogo de uso restrito] da Lei 10.826/03
- Art. 180 [receptação]
- Art. 171 [estelionato]
- Art. 288 [associação criminosa]
- Art. 129, § 9º [lesão corporal em contexto de violência doméstica]
- Art. 147 [ameaça]
- Art. 244-B [corrupção de menores] do ECA (Lei 8.069/90)
- Art. 306 [embriaguez ao volante] do CTB (Lei 9.503/97)
- Art. 213 [estupro]
- Art. 217-A [estupro de vulnerável]

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import Dict, List, Optional, Tuple


# Matriz Canônica de Crimes e Nomen Juris
CRIME_TAXONOMY: Dict[str, Dict] = {
    # Código Penal - Crimes Contra a Pessoa
    "121": {
        "qualificado": "homicídio qualificado",
        "privilegiado": "homicídio privilegiado",
        "culposo": "homicídio culposo",
        "padrao": "homicídio",
    },
    "129": {
        "domestica": "lesão corporal em contexto de violência doméstica",
        "gravissima": "lesão corporal gravíssima",
        "grave": "lesão corporal grave",
        "morte": "lesão corporal seguida de morte",
        "padrao": "lesão corporal",
    },
    "147": {
        "padrao": "ameaça",
    },
    "147-A": {
        "padrao": "perseguição",
    },
    "147-B": {
        "padrao": "violência psicológica contra a mulher",
    },
    # Código Penal - Crimes Contra o Patrimônio
    "155": {
        "qualificado": "furto qualificado",
        "majorado": "furto majorado",
        "privilegiado": "furto privilegiado",
        "padrao": "furto",
    },
    "157": {
        "latrocinio": "latrocínio",
        "qualificado_lesao": "roubo qualificado pela lesão grave",
        "majorado": "roubo majorado",
        "padrao": "roubo",
    },
    "158": {
        "sequestro_relampago": "extorsão mediante restrição da liberdade da vítima",
        "padrao": "extorsão",
    },
    "159": {
        "padrao": "extorsão mediante sequestro",
    },
    "168": {
        "padrao": "apropriação indébita",
    },
    "171": {
        "padrao": "estelionato",
    },
    "180": {
        "qualificado": "receptação qualificada",
        "padrao": "receptação",
    },
    # Código Penal - Crimes Contra a Dignidade Sexual
    "213": {
        "padrao": "estupro",
    },
    "217-A": {
        "padrao": "estupro de vulnerável",
    },
    "218-A": {
        "padrao": "satisfação de lascívia mediante presença de criança ou adolescente",
    },
    "218-B": {
        "padrao": "favorecimento da prostituição ou exploração sexual de criança ou vulnerável",
    },
    # Código Penal - Crimes Contra a Paz Pública
    "288": {
        "padrao": "associação criminosa",
    },
    "288-A": {
        "padrao": "constituição de milícia privada",
    },
    # Código Penal - Crimes Contra a Fé Pública
    "297": {
        "padrao": "falsificação de documento público",
    },
    "298": {
        "padrao": "falsificação de documento particular",
    },
    "299": {
        "padrao": "falsidade ideológica",
    },
    "304": {
        "padrao": "uso de documento falso",
    },
    "307": {
        "padrao": "falsa identidade",
    },
    # Código Penal - Crimes Contra a Administração Pública
    "312": {
        "padrao": "peculato",
    },
    "317": {
        "padrao": "corrupção passiva",
    },
    "329": {
        "padrao": "resistência",
    },
    "330": {
        "padrao": "desobediência",
    },
    "331": {
        "padrao": "desacato",
    },
    "333": {
        "padrao": "corrupção ativa",
    },
    # Código Penal - Parte Geral (Concursos e Formas de Extensão)
    "14": {
        "tentativa": "tentativa",
        "desarmamento": "porte ilegal de arma de fogo de uso permitido",
        "padrao": "porte ilegal de arma de fogo de uso permitido",
    },
    "29": {
        "padrao": "concurso de pessoas",
    },
    "69": {
        "padrao": "concurso material",
    },
    "70": {
        "padrao": "concurso formal",
    },
    "71": {
        "padrao": "crime continuado",
    },
    # Legislação Extravagante
    # Lei de Drogas (11.343/06)
    "33": {
        "privilegiado": "tráfico privilegiado",
        "padrao": "tráfico de drogas",
    },
    "34": {
        "padrao": "posse de maquinário para fabricação de drogas",
    },
    "35": {
        "padrao": "associação para o tráfico",
    },
    "28": {
        "padrao": "porte de drogas para consumo pessoal",
    },
    # Estatuto do Desarmamento (Lei 10.826/03)
    "12": {
        "padrao": "posse irregular de arma de fogo de uso permitido",
    },
    "16": {
        "padrao": "posse ou porte ilegal de arma de fogo de uso restrito",
    },
    "17": {
        "padrao": "comércio ilegal de arma de fogo",
    },
    "18": {
        "padrao": "tráfico internacional de arma de fogo",
    },
    # Estatuto da Criança e do Adolescente - ECA (Lei 8.069/90)
    "244-B": {
        "padrao": "corrupção de menores",
    },
    "240": {
        "padrao": "produção de pornografia infantil",
    },
    "241-A": {
        "padrao": "compartilhamento de pornografia infantil",
    },
    # Código de Trânsito Brasileiro - CTB (Lei 9.503/97)
    "306": {
        "padrao": "embriaguez ao volante",
    },
    "302": {
        "padrao": "homicídio culposo na direção de veículo automotor",
    },
    "303": {
        "padrao": "lesão corporal culposa na direção de veículo automotor",
    },
    "309": {
        "padrao": "direção de veículo sem habilitação gerando perigo de dano",
    },
    # Organização Criminosa (Lei 12.850/13)
    "2": {
        "padrao": "organização criminosa",
    },
    # Lavagem de Dinheiro (Lei 9.613/98)
    "1": {
        "padrao": "lavagem ou ocultação de bens, direitos e valores",
    },
    # Maria da Penha (Lei 11.340/06)
    "24-A": {
        "padrao": "descumprimento de medidas protetivas de urgência",
    },
}


def get_crime_nomen_juris(art_num: str, context_text: str = "") -> Optional[str]:
    """Retorna o nomen juris correto para o artigo informado à luz do contexto (parágrafos, incisos e leis)."""
    norm_num = art_num.strip().upper()
    data = CRIME_TAXONOMY.get(norm_num)
    if not data:
        return None

    ctx_l = context_text.lower()

    if norm_num == "155":
        if re.search(r"§\s*[4567]", ctx_l) or "qualificad" in ctx_l:
            return data["qualificado"]
        if "§ 1" in ctx_l or "repouso" in ctx_l or "noturno" in ctx_l:
            return data["majorado"]
        if "§ 2" in ctx_l or "privilegiad" in ctx_l:
            return data["privilegiado"]
        return data["padrao"]

    if norm_num == "157":
        if re.search(r"§\s*3[º°]?,?\s*(?:II|2\b|parte\s+final)|latroc[ií]nio|morte", ctx_l, re.I):
            return data["latrocinio"]
        if re.search(r"§\s*3[º°]?,?\s*(?:I|1\b)|les[aã]o\s+grave", ctx_l, re.I):
            return data["qualificado_lesao"]
        if re.search(r"§\s*2[º°]?(?:-[A-Za-z])?|majorad", ctx_l, re.I):
            return data["majorado"]
        return data["padrao"]

    if norm_num == "121":
        if re.search(r"§\s*2|qualificad", ctx_l, re.I):
            return data["qualificado"]
        if re.search(r"§\s*1|privilegiad", ctx_l, re.I):
            return data["privilegiado"]
        if re.search(r"§\s*3|culpos", ctx_l, re.I):
            return data["culposo"]
        return data["padrao"]

    if norm_num == "129":
        if re.search(r"§\s*(?:9|13)|viol[eê]ncia\s+dom[eé]stica|famili|dom[eé]stica|mulher", ctx_l, re.I):
            return data["domestica"]
        if re.search(r"§\s*2|grav[ií]ssima", ctx_l, re.I):
            return data["gravissima"]
        if re.search(r"§\s*1|grave", ctx_l, re.I):
            return data["grave"]
        if re.search(r"§\s*3|morte", ctx_l, re.I):
            return data["morte"]
        return data["padrao"]

    if norm_num == "33":
        if "11.343" in ctx_l or "drogas" in ctx_l or "entorpecente" in ctx_l or "caput" in ctx_l or "tóxico" in ctx_l or not any(k in ctx_l for k in ["constituição", "eleitoral", "ctb"]):
            if "§ 4" in ctx_l or "privilegiad" in ctx_l:
                return data["privilegiado"]
            return data["padrao"]

    if norm_num == "180":
        if "§ 1" in ctx_l or "qualificad" in ctx_l:
            return data["qualificado"]
        return data["padrao"]

    if norm_num == "14":
        if re.search(r"\bII\b|tentat", ctx_l, re.I) and ("10.826" not in ctx_l and "desarmamento" not in ctx_l):
            return data.get("tentativa")
        return data.get("padrao")

    if norm_num in ("12", "14", "16", "17", "18"):
        return data.get("padrao")

    if norm_num == "2":
        if "12.850" in ctx_l or "organização criminosa" in ctx_l or "orcrim" in ctx_l:
            return data.get("padrao")
        return None

    if norm_num == "1":
        if "9.613" in ctx_l or "lavagem" in ctx_l:
            return data.get("padrao")
        return None

    if norm_num == "24-A":
        return data.get("padrao")

    return data.get("padrao")


def annotate_imputation_text(imputation_text: str) -> str:
    """Anota os artigos de uma imputação penal com o respectivo nomen juris entre colchetes.

    Exemplos:
        "Art. 155, § 4º, I e IV, do Código Penal" -> "Art. 155, § 4º, I e IV [furto qualificado], do Código Penal"
        "Art. 157, § 2º, II, do CP" -> "Art. 157, § 2º, II [roubo majorado], do CP"
        "Art. 33, caput da Lei 11.343/06" -> "Art. 33, caput [tráfico de drogas] da Lei 11.343/06"
        "Art. 244-B do ECA" -> "Art. 244-B [corrupção de menores] do ECA"
    """
    if not imputation_text or not imputation_text.strip():
        return imputation_text

    text = imputation_text.strip()

    # Regex para capturar artigos penais com suas especificações completas (parágrafos, incisos, alíneas)
    # Ex: "Art. 155, § 4º, I e IV", "artigo 157, § 2º, II e § 2º-A, I", "art. 33, caput", "art. 244-B", "Art. 2º"
    law_tail_re = (
        r"([,\s]+(?:(?:ambos|todos)\s+)?(?:"
        r"do\s+CP|do\s+C[oó]digo\s+Penal|"
        r"da\s+Lei\s+(?:n[º°\.]?\s*)?[\d\.]+(?:/\d+)?|"
        r"do\s+ECA(?:\s*\([^)]*\))?|do\s+CTB(?:\s*\([^)]*\))?|"
        r"do\s+Estatuto\s+d[oa]\s+[A-Za-zÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõ]+(?:\s*\([^)]*\))?|"
        r"da\s+Lei\s+Maria\s+da\s+Penha|"
        r"da\s+Lei\s+de\s+[A-Za-zÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõ]+"
        r"))?"
    )

    article_pattern = re.compile(
        r"(\b(?:art(?:igo)?s?\.?)\s*(\d+(?:-[A-Za-z])?)[º°]?"
        r"(?:[\s,]+(?:caput|§§?\s*\d+[º°]?(?:-[A-Za-z])?|incisos?\s+[IVXLCDM]+|\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\b|\be\s+(?:§§?\s*\d+[º°]?(?:-[A-Za-z])?|incisos?\s+[IVXLCDM]+|\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\b)|(?:a|ao)\s+(?:§§?\s*\d+[º°]?(?:-[A-Za-z])?|incisos?\s+[IVXLCDM]+|\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\b)|al[íi]neas?\s+[a-z]|letras?\s+[a-z]))*)"
        r"(\s*\[[^\]]+\])?"
        + law_tail_re,
        re.IGNORECASE,
    )

    def replacer(m: re.Match) -> str:
        full_art_clause = m.group(1).strip()
        art_num = m.group(2).strip()
        existing_bracket = m.group(3)
        law_tail = m.group(4) or ""

        if existing_bracket:
            return f"{full_art_clause}{existing_bracket}{law_tail}"

        local_context = f"{full_art_clause} {law_tail}".strip()
        nomen_juris = get_crime_nomen_juris(art_num, local_context) or get_crime_nomen_juris(art_num, f"{local_context} {text}")

        if nomen_juris:
            if law_tail:
                cleaned_tail = law_tail.rstrip()
                if cleaned_tail.startswith(","):
                    rest = cleaned_tail.lstrip(", ")
                    tail_str = f", {rest}" if rest else ", "
                    return f"{full_art_clause} [{nomen_juris}]{tail_str}"
                elif cleaned_tail.strip():
                    return f"{full_art_clause} [{nomen_juris}] {cleaned_tail.strip()}"
                else:
                    return f"{full_art_clause} [{nomen_juris}]"
            else:
                return f"{full_art_clause} [{nomen_juris}]"

        return m.group(0)

    annotated = article_pattern.sub(replacer, text)
    annotated = re.sub(r"[ \t]+", " ", annotated).strip()
    return annotated

