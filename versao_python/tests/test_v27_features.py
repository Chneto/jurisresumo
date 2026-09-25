"""Unit tests for v2.7 Features:
- State organs blacklist filter (anti-delegacia/estado/defensoria)
- Chronological sorting and date mask DD/MM/AA
- Vocative stripping in facts narrative
- Adaptive JEV/LEYA learning store and feedback loop
- FastAPI /api/feedback endpoint

Autor: FChNeto
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.engines.offline_engine import (
    OfflineExtractionEngine,
    STATE_ORGANS_BLACKLIST_REGEX,
    _format_date_short,
    _parse_date_sort_key,
)
from app.core.models import PJeDocument, HistoryItem, Defendant
from app.core.learning_store import LearningStore
from app.core.jev_decision_engine import JEVDecisionEngine
from app.main import app


def test_state_organs_blacklist():
    """Ensures state organs mistakenly listed in the passive pole are detected and discarded."""
    test_organs = [
        "DELEGACIA DE PLANTÃO",
        "Delegacia de Polícia Civil - Zona Sul",
        "ESTADO DO RIO GRANDE DO NORTE",
        "Estado da Paraíba",
        "DEFENSORIA PÚBLICA DO ESTADO",
        "Ministério Público Estadual",
        "Comando Geral da PM",
        "Vara Criminal de Natal",
        "Central de Flagrantes",
        "DP de Macaíba",
    ]
    for organ in test_organs:
        assert STATE_ORGANS_BLACKLIST_REGEX.search(organ) is not None, f"Failed to match state organ: {organ}"

    real_defendants = [
        "JOÃO DA SILVA",
        "MARIA DE FÁTIMA SOUZA",
        "LUCAS PEREIRA GOMES",
        "ANTONIO CARLOS",
    ]
    for d in real_defendants:
        assert STATE_ORGANS_BLACKLIST_REGEX.search(d) is None, f"False positive on real person: {d}"


def test_format_date_short_mask():
    """Ensures the strict DD/MM/AA date mask is enforced."""
    assert _format_date_short("14/10/2025") == "14/10/25"
    assert _format_date_short("05/04/1977") == "05/04/77"
    assert _format_date_short("2/3/2026") == "02/03/26"
    assert _format_date_short("31-12-2024") == "31/12/24"
    assert _format_date_short("14/10/25") == "14/10/25"


def test_parse_date_sort_key():
    """Ensures ascending chronological sorting handles years, months, and days properly."""
    k1 = _parse_date_sort_key("15/01/24", "100")
    k2 = _parse_date_sort_key("10/06/24", "101")
    k3 = _parse_date_sort_key("01/02/25", "102")
    k4 = _parse_date_sort_key("20/12/25", "103")

    assert k1 < k2 < k3 < k4

    items = [
        HistoryItem(date_str="20/12/25", description="Decisão final", doc_id="4"),
        HistoryItem(date_str="15/01/24", description="Denúncia", doc_id="1"),
        HistoryItem(date_str="01/02/25", description="Audiência", doc_id="3"),
        HistoryItem(date_str="10/06/24", description="Citação", doc_id="2"),
    ]
    items.sort(key=lambda it: _parse_date_sort_key(it.date_str, it.doc_id))

    sorted_dates = [it.date_str for it in items]
    assert sorted_dates == ["15/01/24", "10/06/24", "01/02/25", "20/12/25"]


def test_vocatives_stripping_in_narrative():
    """Ensures judge vocatives and ministerial salutations are stripped from factual narrative."""
    engine = OfflineExtractionEngine()
    raw_denuncia = """
AO JUÍZO DE DIREITO DA 1ª VARA CRIMINAL DA COMARCA DE NATAL/RN
O MINISTÉRIO PÚBLICO DO ESTADO DO RIO GRANDE DO NORTE, por seu Promotor de Justiça, vem perante Vossa Excelência oferecer DENÚNCIA em desfavor de FULANO DE TAL:
pela prática dos fatos delituosos a seguir narrados:

No dia 15 de janeiro de 2025, por volta das 22h, na Avenida Salgado Filho, o denunciado subtraiu para si, mediante violência exercida com arma de fogo, um aparelho celular pertencente à vítima.
Consta que a guarnição da Polícia Militar realizou diligências e logrou êxito em deter o denunciado na posse da res furtiva.

Termos em que pede deferimento.
ROL DE TESTEMUNHAS:
1. PM Condutor
"""
    paras = engine._extract_clean_narrative(raw_denuncia)
    assert len(paras) >= 2
    for p in paras:
        assert "AO JUÍZO" not in p
        assert "Excelentíssimo" not in p
        assert "vem perante Vossa Excelência" not in p
        assert "Termos em que" not in p
    assert "subtraiu" in paras[0]


def test_learning_store_feedback_loop(tmp_path):
    """Ensures user removals and additions adapt JEV scoring dynamically."""
    store_file = tmp_path / "test_feedback_rules.json"
    store = LearningStore(store_path=store_file)

    # Initially empty
    assert len(store.penalized_terms) == 0
    assert len(store.boosted_terms) == 0
    assert store.compute_learned_adjustment("certidão de juntada genérica de expediente") == 0.0

    # User removes administrative noise
    store.record_removal("Certidão genérica de juntada de expediente bancário sem teor penal")
    assert len(store.penalized_terms) > 0
    assert store.store_path.exists()

    # Score adjustment should now be negative for matching text
    penalty = store.compute_learned_adjustment("certidão genérica de juntada")
    assert penalty < 0.0

    # User adds a substantive item
    store.record_addition("Laudo de lesão corporal anexado comprova materialidade")
    assert len(store.boosted_terms) > 0
    boost = store.compute_learned_adjustment("laudo de lesão corporal")
    assert boost > 0.0

    # Test feedback diff processing
    original_data = {
        "chronological_history": [
            {"doc_id": "111", "description": "Comprovante de pagamento de custas do processo"},
            {"doc_id": "222", "description": "Denúncia oferecida pelo Ministério Público"},
        ],
        "witnesses": [{"name": "Testemunha Desnecessária"}],
        "facts_summary": "Texto original muito longo com detalhes irrelevantes...",
    }
    edited_data = {
        "chronological_history": [
            {"doc_id": "222", "description": "Denúncia oferecida pelo Ministério Público"},
            {"doc_id": "333", "description": "Decisão liminar de prisão preventiva do acusado"},
        ],
        "witnesses": [],
        "facts_summary": "Resumo objetivo.",
    }
    stats = store.record_feedback(original_data, edited_data)
    assert stats["removals"] >= 2  # History item 111 + witness + facts
    assert stats["additions"] >= 1  # History item 333


def test_api_feedback_endpoint():
    """Ensures POST /api/feedback receives user edits and returns success."""
    client = TestClient(app)
    payload = {
        "original": {
            "chronological_history": [{"doc_id": "999", "description": "Extrato de conta corrente inútil"}],
            "witnesses": [],
            "facts_summary": "",
        },
        "edited": {
            "chronological_history": [],
            "witnesses": [],
            "facts_summary": "",
        },
    }
    response = client.post("/api/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "stats" in data
    assert data["stats"]["removals"] >= 1
