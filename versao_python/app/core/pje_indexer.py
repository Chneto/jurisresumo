"""High-performance PJe Document Indexer and Page Pruner for TJRN judicial cases.

Parses initial Table of Documents (TOC), matches footer stamps (Num. <ID> - Pág. <P>),
classifies scanned vs native text pages, and provides selective pruning of key legal acts.
"""

import os
import re
from typing import Dict, List, Optional, Set, Tuple

import pymupdf

from app.core.models import IndexTableEntry, PJeDocument
from app.core.ocr_engine import is_scanned_page

# Regex for footer stamp: Num. <ID> - Pág. <P>
FOOTER_STAMP_REGEX = re.compile(
    r"Num\.\s*(\d+)\s*-\s*P[aáAÁ]g\.\s*(\d+)",
    re.IGNORECASE,
)

# Alternative regex for vertical margin stamps (e.g. e-SAJ / TJSP precatórias)
VERTICAL_STAMP_REGEX = re.compile(
    r"(?:fls\.\s*(\d+)|p[aá]gina\s*(\d+))",
    re.IGNORECASE,
)

# Strict classification patterns for key judicial documents
KEY_DOCUMENT_PATTERNS = [
    re.compile(r"den[uú]ncia", re.IGNORECASE),
    re.compile(r"queixa(?:\s*-?\s*crime)?", re.IGNORECASE),
    re.compile(r"peti[cç][aã]o\s*inicial", re.IGNORECASE),
    re.compile(r"decis[aã]o", re.IGNORECASE),
    re.compile(r"despacho", re.IGNORECASE),
    re.compile(r"senten[cç]a", re.IGNORECASE),
    re.compile(r"pron[uú]ncia", re.IGNORECASE),
    re.compile(r"resposta\s*(?:[aà]\s*)?acusa[cç][aã]o", re.IGNORECASE),
    re.compile(r"defesa\s*pr[eé]via", re.IGNORECASE),
    re.compile(r"mandado", re.IGNORECASE),
    re.compile(r"intima[cç][aã]o", re.IGNORECASE),
    re.compile(r"cita[cç][aã]o", re.IGNORECASE),
    re.compile(r"dilig[eê]ncia", re.IGNORECASE),
    re.compile(r"ato\s*positivo", re.IGNORECASE),
    re.compile(r"ato\s*negativo", re.IGNORECASE),
    re.compile(r"edital", re.IGNORECASE),
    re.compile(r"audi[eê]ncia", re.IGNORECASE),
    re.compile(r"anpp|acordo", re.IGNORECASE),
    re.compile(r"of[ií]cio", re.IGNORECASE),
    re.compile(r"apresenta[cç][aã]o\s*de\s*policia", re.IGNORECASE),
    re.compile(r"termo\s*de\s*audi[eê]ncia", re.IGNORECASE),
    re.compile(r"ata\s*de\s*audi[eê]ncia", re.IGNORECASE),
    re.compile(r"ren[uú]ncia", re.IGNORECASE),
    re.compile(r"pris[aã]o", re.IGNORECASE),
    re.compile(r"liberdade", re.IGNORECASE),
    re.compile(r"revoga[cç][aã]o", re.IGNORECASE),
]

# Patterns of documents that are strictly non-essential bulk data (e.g. SIMBA, phone logs)
BULK_EXCLUDE_PATTERNS = [
    re.compile(r"extrato\s*banc[aá]rio", re.IGNORECASE),
    re.compile(r"dados\s*telef[oô]nicos", re.IGNORECASE),
    re.compile(r"quebra\s*de\s*sigilo", re.IGNORECASE),
    re.compile(r"relat[oó]rio\s*t[eé]cnico\s*de\s*an[aá]lise", re.IGNORECASE),
]


def parse_toc_entries(doc: pymupdf.Document) -> Tuple[List[IndexTableEntry], int]:
    """Parses the initial PJe Table of Documents (TOC / Capa de Processo).

    Iterates through the starting pages until the first page bearing a PJe footer stamp
    is encountered. Extracts Id, Data, Documento, and Tipo using coordinate-based column
    grouping.

    Args:
        doc: Open PyMuPDF Document.

    Returns:
        A tuple of (list of IndexTableEntry, number of TOC pages).
    """
    toc_pages: List[int] = []
    for i in range(len(doc)):
        text = doc[i].get_text()
        if FOOTER_STAMP_REGEX.search(text):
            break
        toc_pages.append(i)

    # In case no footer stamps exist at all (fallback), assume first 1-2 pages
    if not toc_pages:
        toc_pages = [0]

    entries: List[IndexTableEntry] = []
    seen_ids: Set[str] = set()

    for p_idx in toc_pages:
        page = doc[p_idx]
        words = page.get_text("words")
        if not words:
            continue

        # Locate the table header line containing 'Documentos' or 'Id.' / 'Tipo'
        start_y = 0.0
        for w in words:
            if w[4] in ("Documentos", "Tipo"):
                start_y = max(start_y, w[3])

        row_words = [w for w in words if w[1] >= start_y]

        # Identify all document IDs (7 to 10 digit integers in column x < 85)
        id_words = [
            w for w in row_words
            if w[0] < 85 and re.match(r"^\d{7,10}$", w[4])
        ]

        for idx, id_w in enumerate(id_words):
            cur_y0 = id_w[1] - 4.0
            next_y0 = id_words[idx + 1][1] - 4.0 if idx + 1 < len(id_words) else 9999.0

            # Gather words belonging vertically to this row
            this_row = [w for w in row_words if cur_y0 <= w[1] < next_y0]

            # Categorize by standard PJe column boundaries
            col_id = [w[4] for w in this_row if w[0] < 85]
            col_data = [w[4] for w in this_row if 85 <= w[0] < 155]
            col_doc = [w[4] for w in this_row if 155 <= w[0] < 415]
            col_tipo = [w[4] for w in this_row if w[0] >= 415]

            doc_id = col_id[0] if col_id else id_w[4]
            date_str = " ".join(col_data)
            doc_name = " ".join(col_doc)
            doc_type = " ".join(col_tipo)

            # Avoid duplicates if any
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                entries.append(
                    IndexTableEntry(
                        doc_id=doc_id,
                        date_str=date_str,
                        doc_name=doc_name,
                        doc_type=doc_type,
                        page_in_toc=p_idx + 1,
                    )
                )

    return entries, len(toc_pages)


def get_page_footer_stamp(page: pymupdf.Page) -> Optional[Tuple[str, int]]:
    """Extracts document ID and subpage number from a page's footer stamp.

    Handles stacked stamps (e.g. redistributed cases) by selecting the stamp
    with the largest y1 coordinate (the lowest on the page).

    Args:
        page: PyMuPDF Page.

    Returns:
        Tuple of (doc_id, subpage_number) or None if not found.
    """
    # Fast path: check the bottom 120 points of the page first
    page_rect = page.rect
    bottom_rect = pymupdf.Rect(0, max(0.0, page_rect.height - 120.0), page_rect.width, page_rect.height)
    bottom_text = page.get_text(clip=bottom_rect)
    b_matches = list(FOOTER_STAMP_REGEX.finditer(bottom_text))
    if b_matches:
        last_m = b_matches[-1]
        try:
            subpage = int(last_m.group(2))
        except ValueError:
            subpage = 1
        return last_m.group(1), subpage

    blocks = page.get_text("blocks")
    matches = []
    for b in blocks:
        # b is (x0, y0, x1, y1, text, block_no, block_type)
        for m in FOOTER_STAMP_REGEX.finditer(b[4]):
            try:
                subpage = int(m.group(2))
            except ValueError:
                subpage = 1
            matches.append((b[3], m.group(1), subpage))

    if matches:
        # Sort by y1 descending to pick the lowest stamp on the page
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1], matches[0][2]

    # Fallback to searching the complete text of the page
    all_text = page.get_text()
    all_matches = list(FOOTER_STAMP_REGEX.finditer(all_text))
    if all_matches:
        last_m = all_matches[-1]
        try:
            subpage = int(last_m.group(2))
        except ValueError:
            subpage = 1
        return last_m.group(1), subpage

    return None


def index_pje_pdf(pdf_path: str) -> Tuple[List[PJeDocument], pymupdf.Document]:
    """Parses index table and footer stamps; returns document catalog and open PyMuPDF Doc.

    Maps 100% of documents to their exact start and end pages (1-indexed),
    and marks whether each document contains scanned pages.

    Args:
        pdf_path: Path to the PJe compiled PDF file.

    Returns:
        Tuple of (List[PJeDocument], open PyMuPDF Document).
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: '{pdf_path}'")

    doc = pymupdf.open(pdf_path)
    entries, toc_count = parse_toc_entries(doc)

    # Map each page to its detected doc_id
    doc_to_pages: Dict[str, List[int]] = {}
    page_scanned_map: Dict[int, bool] = {}

    for i in range(toc_count, len(doc)):
        page_num = i + 1  # 1-indexed
        page = doc[i]

        stamp = get_page_footer_stamp(page)
        if stamp:
            doc_id, _ = stamp
            doc_to_pages.setdefault(doc_id, []).append(page_num)

        # Check scanned status
        page_scanned_map[page_num] = is_scanned_page(page)

    catalog: List[PJeDocument] = []
    known_entry_ids = set()

    for e in entries:
        known_entry_ids.add(e.doc_id)
        pages = doc_to_pages.get(e.doc_id, [])
        if pages:
            start_page = min(pages)
            end_page = max(pages)
            is_scanned = any(page_scanned_map.get(p, False) for p in pages)
        else:
            # Document listed in TOC but has no separate body pages (e.g. 0-length notice)
            start_page = 0
            end_page = 0
            is_scanned = False

        catalog.append(
            PJeDocument(
                doc_id=e.doc_id,
                date_str=e.date_str,
                doc_name=e.doc_name,
                doc_type=e.doc_type,
                start_page=start_page,
                end_page=end_page,
                is_scanned=is_scanned,
            )
        )

    # Interpolate page ranges for documents listed in TOC that lacked explicit footer stamps
    for idx, d in enumerate(catalog):
        if d.start_page == 0 and len(catalog) > 1:
            prev_end = catalog[idx - 1].end_page if idx > 0 and catalog[idx - 1].end_page > 0 else (toc_count + 1)
            next_start = 0
            for j in range(idx + 1, len(catalog)):
                if catalog[j].start_page > 0:
                    next_start = catalog[j].start_page
                    break
            if next_start > prev_end:
                d.start_page = prev_end + 1
                d.end_page = next_start - 1
                d.is_scanned = any(page_scanned_map.get(p, False) for p in range(d.start_page, d.end_page + 1))

    # In case there are documents in body pages not listed in TOC, add them
    for doc_id, pages in doc_to_pages.items():
        if doc_id not in known_entry_ids and pages:
            start_page = min(pages)
            end_page = max(pages)
            is_scanned = any(page_scanned_map.get(p, False) for p in pages)
            catalog.append(
                PJeDocument(
                    doc_id=doc_id,
                    date_str="",
                    doc_name=f"Documento {doc_id}",
                    doc_type="Outros documentos",
                    start_page=start_page,
                    end_page=end_page,
                    is_scanned=is_scanned,
                )
            )

    return catalog, doc


def is_relevant_document(doc_name: str, doc_type: str) -> bool:
    """Evaluates whether a document represents an essential judicial act."""
    text = f"{doc_name} {doc_type}".strip()
    if not text:
        return False

    # Check exclude patterns
    for pat in BULK_EXCLUDE_PATTERNS:
        if pat.search(text):
            return False

    # Check include patterns
    for pat in KEY_DOCUMENT_PATTERNS:
        if pat.search(text):
            return True

    return False


def prune_documents(
    catalog: List[PJeDocument],
    keep_first_page_of_large_docs: bool = False,
) -> List[PJeDocument]:
    """Selectively filters document catalog down to relevant judicial acts.

    Isolates Denúncia, Decisões, Respostas à Acusação, Mandados/Certidões de Intimação,
    audiências, etc., discarding non-essential bulk attachments.

    Args:
        catalog: Full list of PJeDocument entries.
        keep_first_page_of_large_docs: Whether to include initial summary pages.

    Returns:
        List of pruned PJeDocument entries.
    """
    pruned: List[PJeDocument] = []
    for doc in catalog:
        if doc.start_page == 0:
            continue
        if is_relevant_document(doc.doc_name, doc.doc_type):
            pruned.append(doc)

    return pruned


def get_pruned_page_numbers(
    pruned_catalog: List[PJeDocument],
    include_toc: bool = True,
    toc_count: int = 1,
) -> List[int]:
    """Collects unique sorted 1-based page numbers for the pruned document set.

    Args:
        pruned_catalog: List of relevant PJeDocument objects.
        include_toc: Whether to include the first TOC page (page 1) for case metadata.
        toc_count: Number of TOC pages.

    Returns:
        Sorted list of 1-based page numbers.
    """
    pages: Set[int] = set()
    if include_toc and toc_count > 0:
        pages.add(1)

    for doc in pruned_catalog:
        if doc.start_page > 0 and doc.end_page >= doc.start_page:
            for p in range(doc.start_page, doc.end_page + 1):
                pages.add(p)

    return sorted(pages)


def calculate_page_reduction(total_pages: int, pruned_pages: int) -> float:
    """Calculates page reduction percentage: (1 - pruned / total) * 100."""
    if total_pages <= 0:
        return 0.0
    return max(0.0, (1.0 - (pruned_pages / total_pages)) * 100.0)
