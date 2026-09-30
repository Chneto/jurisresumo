"""Unit and integration tests for the Penal Crime Taxonomy module.
Verifies exact nomen juris annotation between brackets across all penal code articles,
special statutes (Lei de Drogas, Desarmamento, ECA, CTB, Maria da Penha, etc.),
combined articles with c/c, and ensures idempotency without duplicating existing brackets.
Autor: FChNeto
"""

import pytest
from app.core.crime_taxonomy import (
    CRIME_TAXONOMY,
    get_crime_nomen_juris,
    annotate_imputation_text,
)


def test_taxonomy_theft_furto():
    """Tests theft variants (simples, qualificado, majorado, privilegiado)."""
    assert annotate_imputation_text("Art. 155, caput, do Código Penal") == "Art. 155, caput [furto], do Código Penal"
    assert annotate_imputation_text("Art. 155, § 4º, I e IV, do CP") == "Art. 155, § 4º, I e IV [furto qualificado], do CP"
    assert annotate_imputation_text("art. 155, § 1º, do CP") == "art. 155, § 1º [furto majorado], do CP"
    assert annotate_imputation_text("Artigo 155, § 2º do Código Penal") == "Artigo 155, § 2º [furto privilegiado] do Código Penal"


def test_taxonomy_robbery_roubo():
    """Tests robbery variants (simples, majorado, qualificado por lesão, latrocínio)."""
    assert annotate_imputation_text("Art. 157, caput, do Código Penal") == "Art. 157, caput [roubo], do Código Penal"
    assert annotate_imputation_text("Art. 157, § 2º, II, do CP") == "Art. 157, § 2º, II [roubo majorado], do CP"
    assert annotate_imputation_text("art. 157, § 2º-A, I, do CP") == "art. 157, § 2º-A, I [roubo majorado], do CP"
    assert annotate_imputation_text("Art. 157, § 3º, II, do Código Penal") == "Art. 157, § 3º, II [latrocínio], do Código Penal"
    assert annotate_imputation_text("Art. 157, § 3º, I, do Código Penal") == "Art. 157, § 3º, I [roubo qualificado pela lesão grave], do Código Penal"


def test_taxonomy_homicide_homicidio():
    """Tests homicide variants (simples, qualificado, culposo, privilegiado)."""
    assert annotate_imputation_text("Art. 121, caput, do CP") == "Art. 121, caput [homicídio], do CP"
    assert annotate_imputation_text("Art. 121, § 2º, I e IV, do Código Penal") == "Art. 121, § 2º, I e IV [homicídio qualificado], do Código Penal"
    assert annotate_imputation_text("Art. 121, § 3º, do Código Penal") == "Art. 121, § 3º [homicídio culposo], do Código Penal"
    assert annotate_imputation_text("Art. 121, § 1º, do Código Penal") == "Art. 121, § 1º [homicídio privilegiado], do Código Penal"


def test_taxonomy_bodily_injury_lesao_corporal():
    """Tests bodily injury variants including domestic violence."""
    assert annotate_imputation_text("Art. 129, caput, do CP") == "Art. 129, caput [lesão corporal], do CP"
    assert annotate_imputation_text("Art. 129, § 9º, do Código Penal") == "Art. 129, § 9º [lesão corporal em contexto de violência doméstica], do Código Penal"
    assert annotate_imputation_text("Art. 129, § 13, do Código Penal") == "Art. 129, § 13 [lesão corporal em contexto de violência doméstica], do Código Penal"
    assert annotate_imputation_text("Art. 129, § 1º, do CP") == "Art. 129, § 1º [lesão corporal grave], do CP"
    assert annotate_imputation_text("Art. 129, § 2º, do CP") == "Art. 129, § 2º [lesão corporal gravíssima], do CP"
    assert annotate_imputation_text("Art. 129, § 3º, do CP") == "Art. 129, § 3º [lesão corporal seguida de morte], do CP"


def test_taxonomy_threat_and_stalking():
    """Tests threat (ameaça), stalking (perseguição), and psychological violence."""
    assert annotate_imputation_text("Art. 147, caput, do CP") == "Art. 147, caput [ameaça], do CP"
    assert annotate_imputation_text("Art. 147-A do Código Penal") == "Art. 147-A [perseguição] do Código Penal"
    assert annotate_imputation_text("Art. 147-B do Código Penal") == "Art. 147-B [violência psicológica contra a mulher] do Código Penal"


def test_taxonomy_drugs_lei_11343():
    """Tests drug trafficking law (Lei 11.343/06)."""
    assert annotate_imputation_text("Art. 33, caput, da Lei 11.343/06") == "Art. 33, caput [tráfico de drogas], da Lei 11.343/06"
    assert annotate_imputation_text("Art. 33, § 4º, da Lei 11.343/06") == "Art. 33, § 4º [tráfico privilegiado], da Lei 11.343/06"
    assert annotate_imputation_text("Art. 35 da Lei 11.343/06") == "Art. 35 [associação para o tráfico] da Lei 11.343/06"
    assert annotate_imputation_text("Art. 28 da Lei 11.343/06") == "Art. 28 [porte de drogas para consumo pessoal] da Lei 11.343/06"
    assert annotate_imputation_text("Art. 34 da Lei 11.343/06") == "Art. 34 [posse de maquinário para fabricação de drogas] da Lei 11.343/06"


def test_taxonomy_weapons_estatuto_desarmamento():
    """Tests Estatuto do Desarmamento (Lei 10.826/03)."""
    assert annotate_imputation_text("Art. 12 da Lei 10.826/03") == "Art. 12 [posse irregular de arma de fogo de uso permitido] da Lei 10.826/03"
    assert annotate_imputation_text("Art. 14 da Lei 10.826/03") == "Art. 14 [porte ilegal de arma de fogo de uso permitido] da Lei 10.826/03"
    assert annotate_imputation_text("Art. 16 da Lei 10.826/03") == "Art. 16 [posse ou porte ilegal de arma de fogo de uso restrito] da Lei 10.826/03"
    assert annotate_imputation_text("Art. 17 da Lei 10.826/03") == "Art. 17 [comércio ilegal de arma de fogo] da Lei 10.826/03"
    assert annotate_imputation_text("Art. 18 da Lei 10.826/03") == "Art. 18 [tráfico internacional de arma de fogo] da Lei 10.826/03"


def test_taxonomy_special_statutes():
    """Tests ECA, CTB, Maria da Penha, Orcrim, and Lavagem."""
    assert annotate_imputation_text("Art. 244-B do ECA") == "Art. 244-B [corrupção de menores] do ECA"
    assert annotate_imputation_text("Art. 306 do CTB") == "Art. 306 [embriaguez ao volante] do CTB"
    assert annotate_imputation_text("Art. 24-A da Lei 11.340/06") == "Art. 24-A [descumprimento de medidas protetivas de urgência] da Lei 11.340/06"
    assert annotate_imputation_text("Art. 2º da Lei 12.850/13") == "Art. 2º [organização criminosa] da Lei 12.850/13"
    assert annotate_imputation_text("Art. 1º da Lei 9.613/98") == "Art. 1º [lavagem ou ocultação de bens, direitos e valores] da Lei 9.613/98"


def test_taxonomy_property_and_sexual_crimes():
    """Tests receptação, estelionato, apropriação indébita, extorsão, estupro."""
    assert annotate_imputation_text("Art. 180, caput, do CP") == "Art. 180, caput [receptação], do CP"
    assert annotate_imputation_text("Art. 180, § 1º, do CP") == "Art. 180, § 1º [receptação qualificada], do CP"
    assert annotate_imputation_text("Art. 171, caput, do CP") == "Art. 171, caput [estelionato], do CP"
    assert annotate_imputation_text("Art. 168 do Código Penal") == "Art. 168 [apropriação indébita] do Código Penal"
    assert annotate_imputation_text("Art. 158 do CP") == "Art. 158 [extorsão] do CP"
    assert annotate_imputation_text("Art. 159 do CP") == "Art. 159 [extorsão mediante sequestro] do CP"
    assert annotate_imputation_text("Art. 213 do CP") == "Art. 213 [estupro] do CP"
    assert annotate_imputation_text("Art. 217-A do CP") == "Art. 217-A [estupro de vulnerável] do CP"
    assert annotate_imputation_text("Art. 288 do Código Penal") == "Art. 288 [associação criminosa] do Código Penal"


def test_taxonomy_combined_charges():
    """Tests multi-crime imputation with c/c and extension clauses."""
    input_text = "Art. 157, § 2º, II, c/c art. 14, II, ambos do CP, c/c art. 244-B do ECA"
    expected = "Art. 157, § 2º, II [roubo majorado], c/c art. 14, II [tentativa], ambos do CP, c/c art. 244-B [corrupção de menores] do ECA"
    assert annotate_imputation_text(input_text) == expected


def test_taxonomy_idempotency():
    """Ensures already bracketed crimes are not double annotated."""
    already_bracketed = "Art. 155, § 4º, I e IV [furto qualificado], do Código Penal"
    assert annotate_imputation_text(already_bracketed) == already_bracketed

    partially_bracketed = "Art. 155 [furto] c/c art. 180 do CP"
    assert annotate_imputation_text(partially_bracketed) == "Art. 155 [furto] c/c art. 180 [receptação] do CP"


def test_taxonomy_no_false_positive_roman_do_cp():
    """Ensures words starting with D (e.g. 'do CP') are not swallowed as Roman numerals."""
    res = annotate_imputation_text("Art. 155, § 4º, I, do CP")
    assert "[furto qualificado]" in res
    assert "do CP" in res
    assert not res.endswith(" o CP")

