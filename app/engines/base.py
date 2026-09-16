"""Base interface for judicial case extraction engines."""

from abc import ABC, abstractmethod
from typing import List, Optional

from app.core.models import HearingSummaryData, PJeDocument


class BaseExtractionEngine(ABC):
    """Abstract base class for all extraction engines."""

    @abstractmethod
    def extract(
        self,
        pdf_path: str,
        pje_catalog: Optional[List[PJeDocument]] = None,
        **kwargs,
    ) -> HearingSummaryData:
        """Extracts structured judicial hearing summary data from a PJe PDF."""
        pass
