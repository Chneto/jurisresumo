# -*- coding: utf-8 -*-
"""Specialized Engine: Text Sanitizer & Typography Organization Engine (TextSanitizerEngine).

Responsible for:
1. Correcting words glued together from PDF extraction and OCR (punctuation, abbreviations, case transitions).
2. Eliminating nonexistent/phantom paragraphs caused by abbreviations ending in dots (art., fls., nº., etc.).
3. Standardizing legal typography, spacing, punctuation, and indentation for DOCX generation and web preview.
4. Preserving verbatim legal text fidelity while removing digital formatting defects.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import re
from typing import List


class TextSanitizerEngine:
    """Specialized engine for typography cleanup, glued word separation, and paragraph normalization."""

    # Abbreviations that end with a dot but DO NOT end a paragraph
    NON_TERMINATING_ABBREVIATIONS = (
        r"art|arts|fl|fls|folha|folhas|pág|págs|n[ºo°]|inc|par|parág|parágrafo|"
        r"c/c|comb|v\.?g|p\.?ex|dr|dra|sr|sra|prof|profa|id|num|doc|caput|al|"
        r"min|exmo|exma|mm|dep|del|v|vs|ref"
    )

    def separate_glued_words(self, text: str) -> str:
        """Separates glued words caused by PDF extraction, punctuation omission, or OCR artifacts."""
        if not text:
            return ""

        s = text

        # 1. Punctuation glued to a capital letter: e.g. "fato.O réu" -> "fato. O réu"
        # Protect decimal numbers like 1.5 or IP 123.456
        s = re.sub(r"([,;:!?])([A-Za-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ])", r"\1 \2", s)
        s = re.sub(r"(\.)([A-ZÁÉÍÓÚÂÊÔÃÕ])", r"\1 \2", s)

        # 2. Legal abbreviations glued to numbers: e.g. "art.155" -> "art. 155", "fls.12" -> "fls. 12"
        s = re.sub(
            rf"\b({self.NON_TERMINATING_ABBREVIATIONS})\.?(\d+)",
            r"\1. \2",
            s,
            flags=re.IGNORECASE,
        )

        # 3. Legal article paragraphs/incisos: e.g. "art. 155,§2º" -> "art. 155, §2º"
        s = re.sub(r"([,;])([§])", r"\1 \2", s)
        s = re.sub(r"(\d)([§])", r"\1 \2", s)

        # 4. Glued lowercase letter to uppercase letter (camelCase artifacts from PDF line flow):
        # e.g. "denúnciaO acusado" -> "denúncia O acusado"
        # Avoid breaking known single words or initials
        s = re.sub(r"([a-záàâãéêíóôõúç])([A-ZÁÉÍÓÚÂÊÔÃÕ])", r"\1 \2", s)

        # 5. Glued words to opening/closing parentheses: e.g. "fato(a" -> "fato (a"
        s = re.sub(r"([a-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ\d])(\()", r"\1 \2", s)
        s = re.sub(r"(\))([a-záàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ\d])", r"\1 \2", s)

        # 6. Numbers glued to common words (e.g. "15de maio" -> "15 de maio", "10horas" -> "10 horas", "art. 155do CP" -> "art. 155 do CP")
        s = re.sub(
            r"(\d+)(de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro))\b",
            r"\1 \2",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(r"(\d+)(horas?)\b", r"\1 \2", s, flags=re.IGNORECASE)
        s = re.sub(r"(\d+)(do\s+CP|do\s+C[oó]digo|da\s+Lei)\b", r"\1 \2", s, flags=re.IGNORECASE)

        # 7. Normalize multiple consecutive spaces (excluding newlines)
        s = re.sub(r"[ \t]+", " ", s)

        return s

    def clean_paragraphs(self, raw_text: str) -> List[str]:
        """Reconstructs authentic paragraphs by unbreaking wrapped lines,
        reflowing hyphenated words, eliminating phantom paragraphs,
        and preserving authentic enumeration / paragraph structures.
        """
        if not raw_text:
            return []

        # First clean glued words
        cleaned_text = self.separate_glued_words(raw_text)

        # Reflow hyphenated words across line breaks (e.g. "delitu-\noso" -> "delituoso")
        cleaned_text = re.sub(
            r"(\b[a-zA-ZÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõ]+)-\s*\n\s*([a-zA-ZÁÉÍÓÚÂÊÔÃÕa-záéíóúâêôãõ]+\b)",
            r"\1\2",
            cleaned_text,
        )

        # Split into preliminary blocks by double newline
        raw_blocks = [b.strip() for b in re.split(r"\n\s*\n+", cleaned_text) if b.strip()]
        paragraphs: List[str] = []

        enum_start_rx = re.compile(
            r"^(?:(?:\d+|[a-z]|[IVXLCDM]+)[\.\)]|[-–•]|§)\s+",
            re.IGNORECASE,
        )

        for block in raw_blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if not lines:
                continue

            current_para_parts: List[str] = []

            for line in lines:
                is_enum_item = bool(enum_start_rx.match(line))
                if is_enum_item and current_para_parts:
                    # Flush current paragraph before starting an enumeration item
                    joined_p = " ".join(current_para_parts)
                    joined_p = re.sub(r"\s+", " ", joined_p).strip()
                    if joined_p:
                        paragraphs.append(joined_p)
                    current_para_parts = [line]
                else:
                    current_para_parts.append(line)

            if current_para_parts:
                joined_p = " ".join(current_para_parts)
                joined_p = re.sub(r"\s+", " ", joined_p).strip()
                if joined_p:
                    paragraphs.append(joined_p)

        # Final filtering: remove empty, whitespace-only or single-character noise paragraphs
        final_paragraphs = [p for p in paragraphs if len(p) > 2]
        return final_paragraphs

    def sanitize_text(self, text: str) -> str:
        """Full pipeline returning clean text with standard double newline paragraph separation."""
        paragraphs = self.clean_paragraphs(text)
        return "\n\n".join(paragraphs)
