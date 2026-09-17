"""Integration tests for FastAPI application and endpoints."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_list_samples():
    response = client.get("/api/samples")
    assert response.status_code == 200
    samples = response.json()
    assert isinstance(samples, list)
    assert len(samples) >= 1
    assert any("0801889" in s["case_number"] for s in samples)


def test_extract_sample_endpoint():
    # Test sample extraction with offline mode
    response = client.post(
        "/api/extract-sample",
        data={"folder_name": "Proc. 0801889-53.2023.8.20.5001", "engine_mode": "offline"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["case_number"] == "0801889-53.2023.8.20.5001"
    assert data["act_type"] == "AIJ"
    assert len(data["defendants"]) >= 1
    assert len(data["chronological_history"]) > 0


def test_generate_docx_endpoint():
    payload = {
        "case_number": "0801889-53.2023.8.20.5001",
        "act_type": "AIJ",
        "hearing_datetime": "31.07.26 às 10h00min",
        "hearing_link": "https://teams.microsoft.com/meet/123",
        "is_in_person": False,
        "prosecutor": "Dr. Jann Polacek Melo Cardoso",
        "defendants": [
            {
                "name": "Jucimarcia Soares da Silva",
                "status": "respondendo em liberdade",
                "subpoena_id": "194381260",
            }
        ],
        "defense_counsel": "Assistida pela Defensoria Pública",
        "qualification_text": "JUCIMARCIA SOARES DA SILVA, brasileira...",
        "imputation_text": "Lesão corporal (art. 129, §9º)",
        "facts_summary": "Consta nos autos...",
        "chronological_history": [
            {
                "date_str": "10/06/23",
                "description": "Denúncia oferecida",
                "doc_id": "101573748",
            }
        ],
        "prosecution_witnesses": [
            {
                "number": 1,
                "name": "Wallace Gomes Santos",
                "role": "vítima",
                "status_id": "Intimado",
            }
        ],
        "defense_witnesses": [],
        "defense_witness_note": "A defesa requereu a oitiva das testemunhas da acusação.",
        "closure_text": "Cordial e respeitosamente,",
    }

    response = client.post("/api/generate-docx", json=payload)
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert len(response.content) > 1000
