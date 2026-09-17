"""High-Fidelity DOCX Generator for Judicial Case Summaries (TJRN / PJe).

Adheres strictly to OpenXML specifications reverse-engineered from reference documents:
- Page setup: A4 portrait, 2.0 cm margins, header/footer = 0
- Font: Verdana 12pt throughout
- Paragraph line spacing: line="454" (lineRule="auto", ~1.89 lines)
- History and witness items: spacing after="283" (14.15 pt / 0.5 cm)
- First-line indent: firstLine="720" (1.27 cm) for narrative and closure paragraphs
- Hyperlinks: blue (#0000ff), single underline, pointing directly to PJe documents
- Highlighting (Marcação):
  * Yellow highlight (w:val="yellow") on all section headers, callouts, and defense notes
  * Bright green highlight (w:val="green") on Promotor, Réus, and Defesa lines
- Bold formatting:
  * Section titles and hearing participants
  * Defendant full names in qualification (capital letters)
  * Penal articles and laws in imputation
- Italic formatting:
  * Observations and special notes in facts summary
- Strict non-bolding for procedural history items, narrative facts, and witnesses

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import io
import re
from pathlib import Path
from typing import Optional

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

from app.core.models import HearingSummaryData


PJE_DOC_URL_TEMPLATE = "https://pje1g.tjrn.jus.br/pje/Processo/ConsultaProcesso/Detalhe/documentoHTML.seam?idBin={doc_id}"


def _add_p(
    doc: docx.Document,
    line: int = 454,
    after: int = 0,
    before: int = 0,
    first_line: int = 0,
    left: int = 0,
    hanging: int = 0,
    align: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.JUSTIFY,
) -> docx.text.paragraph.Paragraph:
    """Adds a paragraph with precise OpenXML spacing and indentation properties."""
    p = doc.add_paragraph()
    p.alignment = align
    pPr = p._p.get_or_add_pPr()

    sp_xml = f'<w:spacing {nsdecls("w")} w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>'
    pPr.append(parse_xml(sp_xml))

    if first_line > 0:
        ind_xml = f'<w:ind {nsdecls("w")} w:firstLine="{first_line}"/>'
        pPr.append(parse_xml(ind_xml))
    elif left > 0 or hanging > 0:
        ind_xml = f'<w:ind {nsdecls("w")} w:left="{left}" w:hanging="{hanging}"/>'
        pPr.append(parse_xml(ind_xml))

    return p


def _add_run(
    p: docx.text.paragraph.Paragraph,
    text: str,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    color: Optional[str] = None,
    highlight: Optional[str] = None,
    font_name: str = "Verdana",
    font_size_pt: int = 12,
) -> docx.text.run.Run:
    """Adds a run with specified typography and optional highlight."""
    r = p.add_run(text)
    r.font.name = font_name
    r.font.size = Pt(font_size_pt)
    if bold:
        r.bold = True
    if italic:
        r.italic = True
    if underline:
        r.underline = True
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    if highlight:
        hl_val = "yellow" if "yellow" in highlight.lower() else "green"
        rPr = r._r.get_or_add_rPr()
        rPr.append(parse_xml(f'<w:highlight {nsdecls("w")} w:val="{hl_val}"/>'))
    return r


def _add_hyperlink(
    p: docx.text.paragraph.Paragraph,
    url: str,
    text: str,
    color: str = "0000ff",
    underline: bool = True,
    bold: bool = False,
    highlight: Optional[str] = None,
    font_name: str = "Verdana",
    font_size_pt: int = 12,
):
    """Adds a native OpenXML hyperlink element to a paragraph with optional highlight."""
    part = p.part
    r_id = part.relate_to(
        url,
        docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK,
        is_external=True,
    )

    hyperlink = parse_xml(f'<w:hyperlink {nsdecls("w", "r")} r:id="{r_id}"/>')
    run = parse_xml(f'<w:r {nsdecls("w")}/>')
    rPr = parse_xml(
        f'<w:rPr {nsdecls("w")}>'
        f'<w:rFonts w:ascii="{font_name}" w:hAnsi="{font_name}" w:cs="{font_name}"/>'
        f'<w:sz w:val="{font_size_pt * 2}"/>'
        f'</w:rPr>'
    )
    if color:
        rPr.append(parse_xml(f'<w:color {nsdecls("w")} w:val="{color}"/>'))
    if underline:
        rPr.append(parse_xml(f'<w:u {nsdecls("w")} w:val="single"/>'))
    if bold:
        rPr.append(parse_xml(f'<w:b {nsdecls("w")}/>'))
    if highlight:
        hl_val = "yellow" if "yellow" in highlight.lower() else "green"
        rPr.append(parse_xml(f'<w:highlight {nsdecls("w")} w:val="{hl_val}"/>'))

    run.append(rPr)
    run.append(parse_xml(f'<w:t {nsdecls("w")}>{text}</w:t>'))
    hyperlink.append(run)
    p._p.append(hyperlink)
    return hyperlink


def _append_text_with_id_links(
    p: docx.text.paragraph.Paragraph,
    text: str,
    bold: bool = False,
    default_color: Optional[str] = None,
    highlight: Optional[str] = None,
):
    """Parses text containing 'ID <number>' or 'IDs <number>' and wraps numeric IDs with hyperlinks."""
    id_pattern = re.compile(r"\b(\d{7,10})\b")
    last_idx = 0

    for match in id_pattern.finditer(text):
        start, end = match.span()
        # Text before the ID
        before_text = text[last_idx:start]
        if before_text:
            _add_run(p, before_text, bold=bold, color=default_color, highlight=highlight)

        doc_id = match.group(1)
        url = PJE_DOC_URL_TEMPLATE.format(doc_id=doc_id)
        _add_hyperlink(p, url=url, text=doc_id, bold=bold, color="0000ff", underline=True, highlight=highlight)
        last_idx = end

    # Remaining text after the last ID
    remaining_text = text[last_idx:]
    if remaining_text:
        _add_run(p, remaining_text, bold=bold, color=default_color, highlight=highlight)


def generate_docx_summary(
    data: HearingSummaryData,
    output_path: Optional[str] = None,
) -> bytes:
    """Builds a production-quality DOCX summary strictly adhering to reference OpenXML specs."""
    doc = docx.Document()

    # 1. Page Setup: A4 Portrait, Margins 2.0 cm, Header/Footer = 0
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.header_distance = Cm(0)
    section.footer_distance = Cm(0)

    # 2. Header Section
    # Title line (P0): Underlined, normal text
    p0 = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    title_text = f"Proc. {data.case_number} {data.act_type} {data.hearing_datetime}"
    _add_run(p0, title_text, underline=True)

    # Meeting Link line (P1): Blue, underlined
    p1 = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    if data.hearing_link and not data.is_in_person:
        _add_hyperlink(p1, url=data.hearing_link, text=data.hearing_link, color="0000ff", underline=True)
    else:
        _add_run(p1, "Audiência Presencial", underline=True)

    # Blank line separator
    _add_p(doc)

    # Resumo Call line (P3): "Segue o resumo da audiência:" (Underlined)
    p3 = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    _add_run(p3, "Segue o resumo da audiência:", underline=True)

    # Blank line separator
    _add_p(doc)

    # Callout line for ANPP or specific scheduled hearings (Yellow highlight + Bold)
    if "ANPP" in data.act_type:
        p_call = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        time_part = data.hearing_datetime.split("às")[-1].strip() if "às" in data.hearing_datetime else data.hearing_datetime
        _add_run(p_call, f"{time_part} - {data.case_number} - {data.act_type}", bold=True, highlight="yellow")
        _add_p(doc)

    # PROMOTOR line: BOLD + BRIGHT GREEN HIGHLIGHT
    p_prom = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    prom_prefix = "PROMOTORES:" if ";" in data.prosecutor else "PROMOTOR:"
    _add_run(p_prom, f"{prom_prefix} {data.prosecutor}", bold=True, highlight="green")

    # Blank line separator
    _add_p(doc)

    # RÉUS lines: BOLD + BRIGHT GREEN HIGHLIGHT, ID hyperlinked
    if len(data.defendants) == 1:
        d = data.defendants[0]
        p_reu = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        gender_prefix = "Ré:" if d.name.strip().endswith("a") or ("a" in d.name.split()[-1].lower() and d.name.endswith("a")) else "Réu:"
        reu_text = f"{gender_prefix} {d.name} - {d.status}"
        if d.subpoena_id:
            reu_text += f" - Intimado ID {d.subpoena_id}"
        elif d.citation_id:
            reu_text += f" - Citado ID {d.citation_id}"
        _append_text_with_id_links(p_reu, reu_text, bold=True, highlight="green")
    elif len(data.defendants) > 1:
        p_reus_hdr = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        _add_run(p_reus_hdr, "Réus:", bold=True, highlight="green")
        for d in data.defendants:
            p_d = _add_p(doc, left=720, hanging=360, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            d_line = f"{d.name} - {d.status}"
            if d.subpoena_id:
                d_line += f" - Intimado ID {d.subpoena_id}"
            elif d.citation_id:
                d_line += f" - Citado ID {d.citation_id}"
            _append_text_with_id_links(p_d, d_line, bold=False, highlight=None)

    # DEFESA line: BOLD + BRIGHT GREEN HIGHLIGHT
    if data.defense_counsel:
        p_def = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        _add_run(p_def, data.defense_counsel, bold=True, highlight="green")

    # Blank line separator
    _add_p(doc)

    is_anpp = "ANPP" in (data.act_type or "")

    # 3. QUALIFICAÇÃO Section: Header BOLD + YELLOW HIGHLIGHT (omitted in ANPP)
    if data.qualification_text and not is_anpp:
        p_q_hdr = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        _add_run(p_q_hdr, "QUALIFICAÇÃO", bold=True, highlight="yellow")

        # Parse qualifications per defendant
        qual_paragraphs = [q.strip() for q in data.qualification_text.split("\n\n") if q.strip()]
        if not qual_paragraphs:
            qual_paragraphs = [data.qualification_text.strip()]

        for q_para in qual_paragraphs:
            p_q = _add_p(doc, first_line=720, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            # Bold the defendant's full name at the start, rest regular
            comma_split = q_para.split(",", 1)
            if len(comma_split) == 2:
                name_part, rest_part = comma_split
                _add_run(p_q, name_part.upper(), bold=True)
                _add_run(p_q, f",{rest_part}", bold=False)
            else:
                _add_run(p_q, q_para, bold=False)

        _add_p(doc)

    # 4. IMPUTAÇÃO Section: Header BOLD + YELLOW HIGHLIGHT (omitted in ANPP)
    if data.imputation_text and not is_anpp:
        p_imp_hdr = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        _add_run(p_imp_hdr, "IMPUTAÇÃO", bold=True, highlight="yellow")

        imp_paragraphs = [imp.strip() for imp in data.imputation_text.split("\n\n") if imp.strip()]
        if not imp_paragraphs:
            imp_paragraphs = [data.imputation_text.strip()]

        penal_art_regex = re.compile(
            r"(\(.*?\)|"
            r"\bart(?:igo)?\.?\s*\d+[ºª\w\s,§/c\.\-]*?(?:do\s+C[oó]digo\s+Penal|do\s+CP|da\s+Lei[^\n,;.]*)?|"
            r"\bLei\s*(?:n[ºo]\.?\s*)?[\d.]+(?:/\d+)?|"
            r"\bC[oó]digo\s+Penal\b|"
            r"\bCP\b)",
            re.IGNORECASE,
        )
        for imp_para in imp_paragraphs:
            p_imp = _add_p(doc, first_line=720, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            # Bold penal articles, statutes, and parenthesized citations
            parts = penal_art_regex.split(imp_para)
            for part in parts:
                if not part:
                    continue
                is_bold = bool(penal_art_regex.fullmatch(part) or (part.startswith("(") and part.endswith(")")))
                _add_run(p_imp, part, bold=is_bold)

        _add_p(doc)

    # 5. RESUMO DOS FATOS Section: Header BOLD + YELLOW HIGHLIGHT
    if data.facts_summary:
        p_fatos_hdr = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        _add_run(p_fatos_hdr, "RESUMO DOS FATOS", bold=True, highlight="yellow")

        # Special OBS block for ANPP / desmembramento in italic
        if data.special_notes:
            p_obs = _add_p(doc, first_line=720, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            _add_run(p_obs, data.special_notes, italic=True)

        facts_paragraphs = [f.strip() for f in data.facts_summary.split("\n\n") if f.strip()]
        if not facts_paragraphs:
            facts_paragraphs = [data.facts_summary.strip()]

        for f_para in facts_paragraphs:
            p_f = _add_p(doc, first_line=720, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            _append_text_with_id_links(p_f, f_para, bold=False)

        _add_p(doc)

    # 6. HISTÓRICO PROCESSUAL Section: Header BOLD + YELLOW HIGHLIGHT (omitted in ANPP)
    if data.chronological_history and not is_anpp:
        p_hist_hdr = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        _add_run(p_hist_hdr, "HISTÓRICO PROCESSUAL", bold=True, highlight="yellow")

        for item in data.chronological_history:
            # Each history item: strictly REGULAR (no bold), spacing after=283 (14.15 pt)
            p_h = _add_p(doc, after=283, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            url = item.pje_url or PJE_DOC_URL_TEMPLATE.format(doc_id=item.doc_id)

            prefix_str = f"{item.date_str}: {item.description} (ID "
            _add_run(p_h, prefix_str, bold=False)
            _add_hyperlink(p_h, url=url, text=item.doc_id, color="0000ff", underline=True, bold=False)
            _add_run(p_h, ")", bold=False)

        _add_p(doc)

    # 7. TESTEMUNHAS Section: Header BOLD + YELLOW HIGHLIGHT (omitted in ANPP)
    if (data.prosecution_witnesses or data.defense_witnesses or data.defense_witness_note) and not is_anpp:
        p_test_hdr = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        _add_run(p_test_hdr, "TESTEMUNHAS DE ACUSAÇÃO:", bold=True, highlight="yellow")

        if data.prosecution_witnesses:
            for w in data.prosecution_witnesses:
                p_w = _add_p(doc, after=283, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
                w_str = f"{w.number:02d}) {w.name} - {w.role}"
                if w.status_id:
                    w_str += f" - {w.status_id}"
                _append_text_with_id_links(p_w, w_str, bold=False)

        # Defense witnesses
        if data.defense_witnesses:
            p_def_hdr = _add_p(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            _add_run(p_def_hdr, "TESTEMUNHAS DE DEFESA:", bold=True, highlight="yellow")
            for w in data.defense_witnesses:
                p_dw = _add_p(doc, after=283, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
                dw_str = f"{w.number:02d}) {w.name}"
                if w.status_id:
                    dw_str += f" - {w.status_id}"
                _append_text_with_id_links(p_dw, dw_str, bold=False)
        elif data.defense_witness_note:
            p_note = _add_p(doc, after=142, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            # In reference models, standard defense note is BOLD with YELLOW HIGHLIGHT
            _add_run(p_note, data.defense_witness_note, bold=True, highlight="yellow")

        _add_p(doc)

    # 8. Fechamento Formal: Regular, first-line indent 1.27 cm
    p_close = _add_p(doc, first_line=720, after=142, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    _add_run(p_close, data.closure_text, bold=False)

    # Save to buffer or file
    buf = io.BytesIO()
    doc.save(buf)
    file_bytes = buf.getvalue()

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(file_bytes)

    return file_bytes
