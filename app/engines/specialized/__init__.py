# -*- coding: utf-8 -*-
"""Specialized multi-engine package for judicial case extraction and corroboration.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

from app.engines.specialized.capa_parties_engine import CapaPartiesEngine
from app.engines.specialized.hearing_details_engine import HearingDetailsEngine
from app.engines.specialized.classification_hierarchy_engine import ClassificationHierarchyEngine
from app.engines.specialized.prosecutor_engine import ProsecutorEngine
from app.engines.specialized.defense_counsel_engine import DefenseCounselEngine
from app.engines.specialized.defendant_qualification_engine import DefendantQualificationEngine
from app.engines.specialized.imputation_taxonomy_engine import ImputationTaxonomyEngine
from app.engines.specialized.facts_narrative_engine import FactsNarrativeEngine
from app.engines.specialized.chronological_history_engine import ChronologicalHistoryEngine
from app.engines.specialized.witness_subpoena_engine import WitnessSubpoenaEngine
from app.engines.specialized.corroboration_consensus_engine import (
    CorroborationConsensusEngine,
    ConsensusAuditReport,
)

__all__ = [
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
