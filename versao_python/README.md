# JURISRESUMO — Versão Backend Python (FastAPI + Uvicorn)
**Autor:** FChNeto

Esta pasta contém a aplicação completa e autônoma em Python com backend FastAPI, Uvicorn, indexador de autos PJe (`pje_indexer.py`), motor offline (`offline_engine.py`), motor de IA (`gemini_engine.py`), gerador DOCX OpenXML (`docx_generator.py`) e suíte de testes E2E Tiers 1-4.

## Como Executar
1. Dê dois cliques em `Iniciar_JURISRESUMO.vbs` (ou execute `python run.py`).
2. O servidor local iniciará na porta 8000 e abrirá seu navegador automaticamente em `http://127.0.0.1:8000`.

## Como Rodar os Testes
```bash
pytest tests/
# ou
python tests/run_all_tests.py
```
