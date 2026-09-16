"""Canonical Pydantic models for the Judicial Case Summary application.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

from typing import List, Optional
from pydantic import BaseModel, Field


class Defendant(BaseModel):
    """Represents a defendant in the criminal proceeding."""
    name: str
    status: str = "Em liberdade"  # e.g., "solto", "preso provisoriamente", "réu preso"
    citation_id: Optional[str] = None
    subpoena_id: Optional[str] = None
    qualification: Optional[str] = None


class Witness(BaseModel):
    """Represents a witness (prosecution or defense)."""
    number: int
    name: str
    role: str = "Testemunha"  # e.g., "Vítima", "Policial Militar", "Testemunha Presencial"
    status_id: Optional[str] = None


class HistoryItem(BaseModel):
    """Represents an item in the chronological procedural history."""
    date_str: str  # DD/MM/AA
    description: str
    doc_id: str
    pje_url: Optional[str] = None


class HearingSummaryData(BaseModel):
    """Complete structured judicial hearing summary data adhering to the 6 canonical sections."""
    case_number: str
    act_type: str = "AIJ"  # AIJ, ANPP, PAnP
    hearing_datetime: str
    hearing_link: Optional[str] = None
    is_in_person: bool = False
    prosecutor: str
    defendants: List[Defendant] = Field(default_factory=list)
    defense_counsel: str
    qualification_text: Optional[str] = None
    imputation_text: Optional[str] = None
    facts_summary: Optional[str] = None
    chronological_history: List[HistoryItem] = Field(default_factory=list)
    prosecution_witnesses: List[Witness] = Field(default_factory=list)
    defense_witnesses: List[Witness] = Field(default_factory=list)
    defense_witness_note: Optional[str] = None
    special_notes: Optional[str] = None  # for ANPP conditions or PAnP
    closure_text: str = "Cordial e respeitosamente,"


class IndexTableEntry(BaseModel):
    """An entry extracted from the PJe initial Table of Documents (Capa de Processo)."""
    doc_id: str
    date_str: str
    doc_name: str
    doc_type: str
    page_in_toc: Optional[int] = None


class PJeDocument(BaseModel):
    """A document identified in the compiled PJe PDF with mapped start and end pages."""
    doc_id: str
    date_str: str
    doc_name: str
    doc_type: str
    start_page: int  # 1-indexed
    end_page: int    # 1-indexed
    is_scanned: bool = False


class OCRLine(BaseModel):
    """A single recognized line from the OCR engine with text, confidence, and bounding box."""
    text: str
    confidence: float = 1.0
    box: Optional[List[List[float]]] = None


class OCRResult(BaseModel):
    """Structured result of local OCR execution on a scanned page."""
    text: str
    lines: List[OCRLine] = Field(default_factory=list)
    page_number: Optional[int] = None
    is_scanned: bool = True
