# -*- coding: utf-8 -*-
"""Extraction engines package for judicial summary generation.

Dual-Engine & Multi-Agent Architecture:
- BaseExtractionEngine: Abstract base contract
- GeminiExtractionEngine: Generative AI Engine (Mode 1)
- OfflineExtractionEngine: Local Deterministic Multi-Engine Orchestrator (Mode 2)
- Specialized Engines (1 to 10): Modular domain agents with cross-corroboration and consensus

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

from typing import Optional

from app.engines.base import BaseExtractionEngine
from app.engines.gemini_engine import GeminiExtractionEngine
from app.engines.offline_engine import OfflineExtractionEngine
from app.engines.specialized import (
    CapaPartiesEngine,
    ChronologicalHistoryEngine,
    ClassificationHierarchyEngine,
    CorroborationConsensusEngine,
    DefendantQualificationEngine,
    DefenseCounselEngine,
    FactsNarrativeEngine,
    HearingDetailsEngine,
    ImputationTaxonomyEngine,
    ProsecutorEngine,
    WitnessSubpoenaEngine,
    ConsensusAuditReport,
)


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
    "CapaPartiesEngine",
    "HearingDetailsEngine",
    "ClassificationHierarchyEngine",
    "ProsecutorEngine",
    "DefenseCounselEngine",
    "DefendantQualificationEngine",
    "ImputationTaxonomyEngine",
    "FactsNarrativeEngine",
    "ChronologicalHistoryEngine",
    "WitnessSubpoenaEngine",
    "CorroborationConsensusEngine",
    "ConsensusAuditReport",
]
