"""
JURISRESUMO - Test Suite for v3.1 Six Enhancements
Desenvolvido por FChNeto

Tests covering:
1. Factual narrative limits & full facts preservation (no 6-paragraph truncation).
2. Hearing date extraction from judicial scheduling order (ignoring digital signature timestamps).
3. Representation positioning (Assistente below Promotor, Defesa below respective defendants).
4. Spelling & organization engine (TextSanitizerEngine: glued words & abbreviation protection).
5. Subpoena/Diligence per-party mapping (PartySubpoenaEngine: no false fallbacks or cross-leakage).
6. Canonical Word download filename generation.
"""

import pytest
from app.core.models import Defendant, HearingSummaryData, HistoryItem
from app.engines.specialized.text_sanitizer_engine import TextSanitizerEngine
from app.engines.specialized.party_subpoena_engine import PartySubpoenaEngine
from app.engines.specialized.facts_narrative_engine import FactsNarrativeEngine
from app.engines.specialized.hearing_details_engine import HearingDetailsEngine
from app.generators.docx_generator import generate_docx_summary, build_canonical_docx_filename


class TestFactualNarrativeLimits:
    """Requirement 1: Eliminate truncations that cut off narrative facts."""

    def test_narrative_preserves_more_than_six_paragraphs(self):
        engine = FactsNarrativeEngine()
        paragraphs = [
            f"Consta dos autos que no dia {i+1} de janeiro de 2024, o denunciado praticou o delito de estelionato ao enganar a vítima {i+1}."
            for i in range(12)
        ]
        complaint_text = "DOS FATOS\n\n" + "\n\n".join(paragraphs) + "\n\nROL DE TESTEMUNHAS\n1. Fulano"

        extracted = engine.extract_clean_narrative(complaint_text)
        assert len(extracted) == 12, f"Expected 12 paragraphs, got {len(extracted)}"
        assert "vítima 12" in extracted[-1]

    def test_abbreviations_do_not_create_phantom_paragraphs(self):
        engine = FactsNarrativeEngine()
        raw_text = (
            "DOS FATOS\n"
            "O acusado violou as disposições constantes no art.\n"
            "129, caput, do Código Penal Brasileiro, conforme fls.\n"
            "15 dos autos de inquérito policial nº.\n"
            "2024.123456 instaurado pela autoridade competente.\n\n"
            "Em seguida, empreendeu fuga do local dos fatos.\n\n"
            "ROL DE TESTEMUNHAS"
        )
        extracted = engine.extract_clean_narrative(raw_text)
        # Should not split the first thought into 4 separate paragraphs due to 'art.', 'fls.', 'nº.'
        assert len(extracted) == 2, f"Expected 2 coherent paragraphs, got {len(extracted)}"
        assert "art. 129" in extracted[0] or "art." in extracted[0]


class TestHearingDespachoDateExtraction:
    """Requirement 2: Extract date/time determined by the Judge, not the signature timestamp."""

    def test_judicial_scheduled_date_prioritized_over_digital_signature(self):
        engine = HearingDetailsEngine()
        despacho_text = (
            "ESTADO DO RIO GRANDE DO NORTE - PODER JUDICIÁRIO\n"
            "Num. 99887766 - Pág. 1\n"
            "Assinado eletronicamente em 10/01/2026 às 15:42:30 por Magistrado Substituto\n\n"
            "DESPACHO\n\n"
            "Vistos etc.\n\n"
            "Para a realização da audiência de instrução e julgamento, designo o dia "
            "28 de maio de 2026 às 10h30min, a ser realizada por videoconferência.\n"
            "Intimem-se as partes e testemunhas.\n\n"
            "Natal/RN, 10 de janeiro de 2026.\n"
            "Juiz de Direito"
        )
        dt = engine.parse_datetime_from_text(despacho_text)
        assert dt is not None
        # Must be the hearing realization date (28.05.26 às 10h30min), NOT the signature date (10.01.26 às 15h42min)
        assert "28.05.26" in dt or "28.05.2026" in dt
        assert "10h30min" in dt
        assert "15h42min" not in dt

    def test_numeric_date_with_scheduling_verb(self):
        engine = HearingDetailsEngine()
        text = (
            "Data da assinatura: 15/02/2026 às 18:00\n"
            "Assinado eletronicamente por Diretor de Secretaria\n\n"
            "Fica designada a audiência de instrução para o dia 14/08/2026 às 09:00.\n"
        )
        dt = engine.parse_datetime_from_text(text)
        assert dt is not None
        assert "14.08.26" in dt or "14.08.2026" in dt
        assert "09h00min" in dt


class TestRepresentationPositioning:
    """Requirement 3: Position defense counsel and assistant prosecutor below respective parties."""

    def test_single_defendant_counsel_and_assistente_in_docx(self):
        data = HearingSummaryData(
            case_number="0801234-56.2026.8.20.5001",
            act_type="AIJ",
            hearing_datetime="20.08.26 às 10h00min",
            hearing_link="https://meet.google.com/abc-defg-hij",
            prosecutor="Dr. Promotor Acusador",
            assistente_acusacao="Dr. Advogado da Vítima",
            defendants=[
                Defendant(
                    name="JOÃO DA SILVA",
                    status="solto",
                    subpoena_id="11223344",
                    counsel="Dra. Defensora Particular OAB/RN 9999",
                )
            ],
            defense_counsel="Defensoria Pública Geral",
            qualification_text="JOÃO DA SILVA, brasileiro, solteiro...",
            imputation_text="Art. 155 do CP",
            facts_summary="Consta que o réu subtraiu coisa alheia móvel.",
        )
        docx_bytes = generate_docx_summary(data)
        assert len(docx_bytes) > 1000

        # Verify OpenXML content
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")

        # Assistente de acusação must appear after prosecutor
        prom_pos = doc_xml.find("PROMOTOR: Dr. Promotor Acusador")
        asst_pos = doc_xml.find("Assistente de Acusação: Dr. Advogado da Vítima")
        reu_pos = doc_xml.find("JOÃO DA SILVA")
        def_pos = doc_xml.find("Dra. Defensora Particular OAB/RN 9999")

        assert prom_pos != -1
        assert asst_pos != -1
        assert prom_pos < asst_pos < reu_pos
        assert reu_pos < def_pos

    def test_multi_defendant_individual_counsel_positioning(self):
        data = HearingSummaryData(
            case_number="0805555-55.2026.8.20.5001",
            act_type="AIJ",
            hearing_datetime="25.09.26 às 14h00min",
            prosecutor="Dr. Promotor",
            defendants=[
                Defendant(name="RÉU UM", status="preso", subpoena_id="10101010", counsel="Dr. Advogado Um"),
                Defendant(name="RÉU DOIS", status="solto", subpoena_id="20202020", counsel="Dra. Advogada Dois"),
            ],
            defense_counsel="Defensoria Pública",
            qualification_text="RÉU UM... RÉU DOIS...",
            imputation_text="Art. 157 do CP",
            facts_summary="Fatos...",
        )
        docx_bytes = generate_docx_summary(data)
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")

        r1_pos = doc_xml.find("RÉU UM")
        d1_pos = doc_xml.find("Dr. Advogado Um")
        r2_pos = doc_xml.find("RÉU DOIS")
        d2_pos = doc_xml.find("Dra. Advogada Dois")

        assert r1_pos < d1_pos < r2_pos < d2_pos


class TestTextSanitizerEngine:
    """Requirement 4: Dedicated spelling and organization engine for glued words and abbreviations."""

    def test_separate_glued_words(self):
        sanitizer = TextSanitizerEngine()

        # Legal article glued
        assert sanitizer.separate_glued_words("incidindo no art.129 e art.155 do CP") == "incidindo no art. 129 e art. 155 do CP"
        assert sanitizer.separate_glued_words("conforme fls.45 dos autos") == "conforme fls. 45 dos autos"

        # Period followed immediately by capital letter
        assert sanitizer.separate_glued_words("oferecer a presente denúncia.O réu agiu com dolo.") == "oferecer a presente denúncia. O réu agiu com dolo."

        # Comma followed by letter
        assert sanitizer.separate_glued_words("apurou-se o fato,com riqueza de detalhes") == "apurou-se o fato, com riqueza de detalhes"

        # Parenthesis glued
        assert sanitizer.separate_glued_words("incurso no art. 121(homicídio)qualificado") == "incurso no art. 121 (homicídio) qualificado"

    def test_clean_paragraphs_preserves_abbreviations(self):
        sanitizer = TextSanitizerEngine()
        raw = "Parágrafo com art.\n14 do CP e fls.\n22 dos autos.\n\nSegundo parágrafo legítimo."
        paras = sanitizer.clean_paragraphs(raw)
        assert len(paras) == 2
        assert "art. 14 do CP e fls. 22" in paras[0]


class TestPartySubpoenaEngine:
    """Requirement 5: Strict diligence mapping per party without false fallbacks or cross-leakage."""

    def test_party_subpoena_strict_matching_and_no_cross_leakage(self):
        from app.core.models import PJeDocument
        engine = PartySubpoenaEngine()
        catalog = [
            PJeDocument(doc_id="11111111", doc_name="Certidão de Mandado", doc_type="Certidão", date_str="01/01/26", start_page=1, end_page=1),
            PJeDocument(doc_id="22222222", doc_name="Certidão de Mandado", doc_type="Certidão", date_str="01/01/26", start_page=2, end_page=2),
            PJeDocument(doc_id="33333333", doc_name="Certidão Negativa", doc_type="Certidão", date_str="01/01/26", start_page=3, end_page=3),
        ]
        engine._doc_cache["11111111"] = "certifico que intimei o réu joão batista no endereço indicado."
        engine._doc_cache["22222222"] = "certifico que intimei a testemunha maria silva."
        engine._doc_cache["33333333"] = "certifico que deixei de intimar o réu pedro santos, pois não localizado (contrafé negativa)."

        party_map = engine.build_party_diligences_map(catalog, None, ["JOÃO BATISTA", "PEDRO SANTOS", "CARLOS SOUZA"])

        # João Batista should have subpoena 11111111
        subp_j, cit_j, st_j = engine.get_defendant_diligence("JOÃO BATISTA", party_map)
        assert subp_j == "11111111"

        # Pedro Santos had a negative diligence; must NOT be marked with subpoena_id
        subp_p, cit_p, st_p = engine.get_defendant_diligence("PEDRO SANTOS", party_map)
        assert subp_p is None
        assert st_p is not None and "negativa" in st_p.lower()

        # Carlos Souza is not mentioned; must NOT receive any fallback ID from other parties
        subp_c, cit_c, st_c = engine.get_defendant_diligence("CARLOS SOUZA", party_map)
        assert subp_c is None


class TestCanonicalDocxFilename:
    """Requirement 6: Strictly canonical filename format: '{hora}, {data} - Resumo nº {processo} - {tipo}.docx'."""

    def test_canonical_filename_structure(self):
        data = HearingSummaryData(
            case_number="0801889-53.2023.8.20.5001",
            act_type="AIJ",
            hearing_datetime="31.07.26 às 10h00min",
            prosecutor="Dr. Promotor",
            defense_counsel="Defensoria Pública",
            defendants=[Defendant(name="RÉU", status="solto")],
            qualification_text="...",
            imputation_text="...",
            facts_summary="...",
        )
        fn = build_canonical_docx_filename(data)
        assert fn == "10h00min, 31.07.2026 - Resumo nº 0801889-53.2023.8.20.5001 - AIJ.docx"

    def test_canonical_filename_with_alternative_date_formats(self):
        data1 = HearingSummaryData(
            case_number="0820550-12.2025.8.20.5001",
            act_type="AIJ",
            hearing_datetime="17/07/2026 às 09:00",
            prosecutor="Dr. Promotor",
            defense_counsel="Defensoria Pública",
            defendants=[Defendant(name="RÉU", status="solto")],
            qualification_text="...",
            imputation_text="...",
            facts_summary="...",
        )
        fn1 = build_canonical_docx_filename(data1)
        assert fn1 == "09h00min, 17.07.2026 - Resumo nº 0820550-12.2025.8.20.5001 - AIJ.docx"

        data2 = HearingSummaryData(
            case_number="0860849-94.2026.8.20.5001",
            act_type="ANPP",
            hearing_datetime="24.07.2026 às 11h25",
            prosecutor="Dr. Promotor",
            defense_counsel="Defensoria Pública",
            defendants=[Defendant(name="RÉU", status="solto")],
            qualification_text="...",
            imputation_text="...",
            facts_summary="...",
        )
        fn2 = build_canonical_docx_filename(data2)
        assert fn2 == "11h25min, 24.07.2026 - Resumo nº 0860849-94.2026.8.20.5001 - ANPP.docx"

    def test_canonical_filename_strips_proc_prefix_and_sanitizes_chars(self):
        data = HearingSummaryData(
            case_number="Proc. nº 0801889-53.2023.8.20.5001",
            act_type="AIJ/Virtual",
            hearing_datetime="31.07.26 às 10h00min",
            prosecutor="Dr. Promotor",
            defense_counsel="Defensoria Pública",
            defendants=[Defendant(name="RÉU", status="solto")],
            qualification_text="...",
            imputation_text="...",
            facts_summary="...",
        )
        fn = build_canonical_docx_filename(data)
        assert fn == "10h00min, 31.07.2026 - Resumo nº 0801889-53.2023.8.20.5001 - AIJ-Virtual.docx"
        assert "Proc." not in fn
        assert "/" not in fn


class TestAdversarialAuditedFixes:
    """Rigorous tests specifically covering the bugs identified during adversarial review."""

    def test_multi_defendant_no_green_highlight_on_individual_defendants(self):
        """AGENTS.md rule: In multiple defendants, ONLY 'Réus:' gets green highlight.
        Individual defendants and defense below have NO green highlight!
        """
        import io, zipfile, xml.etree.ElementTree as ET
        data = HearingSummaryData(
            case_number="0805555-55.2026.8.20.5001",
            act_type="AIJ",
            hearing_datetime="25.09.26 às 14h00min",
            prosecutor="Dr. Promotor",
            defendants=[
                Defendant(name="RÉU UM", status="preso", subpoena_id="10101010", counsel="Dr. Advogado Um"),
                Defendant(name="RÉU DOIS", status="solto", subpoena_id="20202020", counsel="Dra. Advogada Dois"),
            ],
            defense_counsel="Defensoria Pública",
            qualification_text="RÉU UM... RÉU DOIS...",
            imputation_text="Art. 157 do CP",
            facts_summary="Fatos...",
        )
        docx_bytes = generate_docx_summary(data)
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")

        root = ET.fromstring(doc_xml)
        namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        # Find paragraphs containing RÉU UM and Dr. Advogado Um
        for p in root.findall(".//w:p", namespaces):
            full_text = "".join(t.text for t in p.findall(".//w:t", namespaces) if t.text)
            if "RÉU UM" in full_text or "Dr. Advogado Um" in full_text or "RÉU DOIS" in full_text or "Dra. Advogada Dois" in full_text:
                # Must have NO green highlight
                for highlight in p.findall(".//w:highlight", namespaces):
                    val = highlight.attrib.get(f"{{{namespaces['w']}}}val")
                    assert val != "green", f"Paragraph '{full_text}' must NOT have green highlight!"

        # Ensure 'Réus:' DOES have green highlight
        found_reus_hl = False
        for p in root.findall(".//w:p", namespaces):
            full_text = "".join(t.text for t in p.findall(".//w:t", namespaces) if t.text)
            if full_text.strip() == "Réus:":
                for highlight in p.findall(".//w:highlight", namespaces):
                    if highlight.attrib.get(f"{{{namespaces['w']}}}val") == "green":
                        found_reus_hl = True
        assert found_reus_hl, "Paragraph 'Réus:' must have green highlight!"

    def test_short_substantive_sentences_preserved_in_narrative(self):
        """Ensure short substantive sentences (<= 35 chars) are not silently deleted."""
        engine = FactsNarrativeEngine()
        complaint = (
            "DOS FATOS\n\n"
            "Consta dos autos que no dia dos fatos o réu subtraiu a quantia descrita.\n"
            "A arma foi apreendida.\n"
            "O réu confessou a autoria.\n\n"
            "ROL DE TESTEMUNHAS"
        )
        extracted = engine.extract_clean_narrative(complaint)
        joined = " ".join(extracted)
        assert "A arma foi apreendida." in joined
        assert "O réu confessou a autoria." in joined

    def test_glued_numbers_and_words_fixed(self):
        """Ensure glued numbers and words (e.g. 15de, 10horas, 155do) are separated."""
        sanitizer = TextSanitizerEngine()
        result = sanitizer.separate_glued_words("no dia 15de maio às 10horas com base no art. 155do CP")
        assert "15 de maio" in result
        assert "10 horas" in result
        assert "155 do CP" in result

