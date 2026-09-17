"""Extraction engines package for judicial summary generation."""

from typing import Optional

from app.engines.base import BaseExtractionEngine
from app.engines.gemini_engine import GeminiExtractionEngine
from app.engines.offline_engine import OfflineExtractionEngine


def get_engine(mode: str = "offline", api_key: Optional[str] = None) -> BaseExtractionEngine:
    """Factory function returning the selected extraction engine."""
    mode_lower = mode.lower().strip()
    if mode_lower in ("gemini", "ai", "modo1", "mode1"):
        return GeminiExtractionEngine(api_key=api_key)
    return OfflineExtractionEngine()


__all__ = [
    "BaseExtractionEngine",
    "OfflineExtractionEngine",
    "GeminiExtractionEngine",
    "get_engine",
]
