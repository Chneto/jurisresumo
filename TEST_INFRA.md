# E2E Test Infra: Automated Judicial Case Summary Application

## Test Philosophy
- **Opaque-Box & Requirement-Driven:** Derived strictly from `ORIGINAL_REQUEST.md` and user-facing judicial deliverables, not internal implementation details.
- **Methodology:** Category-Partition, Boundary Value Analysis (BVA), Pairwise Combinatorial Testing, and Real-World Workload Testing across all 9 reference cases in `c:\Users\f201503\Documents\Resumo para audiência`.
- **Pass/Fail Semantics:** Strict exit code 0; all test assertions must pass without mocked data or bypassed verifications.

## Feature Inventory & Test Matrix
| # | Feature | Source | Tier 1 (Coverage) | Tier 2 (Boundaries) | Tier 3 (Interactions) |
|---|---|---|:---:|:---:|:---:|
| F01 | Dual Engine Selection | ORIGINAL_REQUEST §R1 | ≥5 cases | Mode toggle, invalid engine error | Mode 1 vs Mode 2 parity |
| F02 | Gemini AI Extraction | ORIGINAL_REQUEST §R1 | ≥5 cases | Missing API key, network timeout | AI extraction with large documents |
| F03 | 100% Offline Extraction | ORIGINAL_REQUEST §R1 | ≥5 cases | Zero-network assertion, corrupt PDF | Offline regex on complex timelines |
| F04 | Offline OCR Integration | ORIGINAL_REQUEST §R1 | ≥5 cases | Pure image pages, noisy scans | Scanned laudos merged with text |
| F05 | PJe Index & Stamp Parsing | ORIGINAL_REQUEST §R2 | ≥5 cases | Multi-page TOC, stacked stamps | Complete 1,004 doc catalog mapping |
| F06 | Cabeçalho Extraction | ORIGINAL_REQUEST §R2 | ≥5 cases | Virtual (Teams/Meet) vs Presencial | Header linked with accused status |
| F07 | Qualificação Extraction | ORIGINAL_REQUEST §R2 | ≥5 cases | Missing CPF/RG, multi-defendants | Upper case bold name + address |
| F08 | Imputação Extraction | ORIGINAL_REQUEST §R2 | ≥5 cases | Single art. vs complex penal combos | Bold articles in parentheses |
| F09 | Resumo dos Fatos | ORIGINAL_REQUEST §R2 | ≥5 cases | Short vs long complaint transcription | Forensic report IDs embedded |
| F10 | Histórico Processual | ORIGINAL_REQUEST §R2 | ≥5 cases | Chronological order, ID format | `DD/MM/AA: [Ato] (ID [num])` |
| F11 | Rol de Testemunhas | ORIGINAL_REQUEST §R2 | ≥5 cases | Acusação only, Defense reiteration | Witness numbered items + ID certidões |
| F12 | Formal Closure | ORIGINAL_REQUEST §R2 | ≥5 cases | Whitespace & canonical phrase | Exact `Cordial e respeitosamente,` |
| F13 | Special Case Formats | Survey Discovery | ≥5 cases | ANPP agreement clauses, PAnP art 366 | ANPP indented OBS block |
| F14 | Modern Web UI | ORIGINAL_REQUEST §R3 | ≥5 cases | Responsive viewports, mobile/desktop | Card state synchronization |
| F15 | Drag-and-Drop PDF Upload | ORIGINAL_REQUEST §R3 | ≥5 cases | Multi-megabyte PDF streaming | Large file buffer handling |
| F16 | Interactive Field Editor | ORIGINAL_REQUEST §R3 | ≥5 cases | Add/remove witnesses & history items | Edited fields reflected in DOCX |
| F17 | Real-Time Summary Preview | ORIGINAL_REQUEST §R3 | ≥5 cases | Live DOM update on field edits | Preview matches export data |
| F18 | High-Fidelity DOCX Generator | ORIGINAL_REQUEST §R4 | ≥5 cases | A4 portrait, 2cm margin, Verdana 12pt | OpenXML byte-compatibility |
| F19 | 1-Click DOCX Download | ORIGINAL_REQUEST §R3 | ≥5 cases | Binary stream integrity, MIME type | Instant download round-trip |
| F20 | Automated E2E Suite | ORIGINAL_REQUEST §R5 | ≥5 cases | CLI & programmatic runner | End-to-end regression validation |

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Reference Case | Features Exercised | Complexity |
|---|---|---|---|---|
| S1 | Standard AIJ Single Accused with Video Intimations | `Proc. 0801889-53.2023.8.20.5001` | F01, F03, F05, F06-F12, F18 | High |
| S2 | Multi-Accused Complex Robbery & PM Witnesses | `Proc. 0820550-12.2025.8.20.5001` | F03, F06, F07, F10, F11, F18 | High |
| S3 | AIJ with Extensive Police Inquérito & Forensic IDs | `Proc. 0821902-39.2024.8.20.5001` | F03, F04, F05, F09, F10, F18 | High |
| S4 | ANPP Hearing with Agreement Conditions & OBS | `Proc. 0860849-94.2026.8.20.5001` | F03, F05, F06, F10, F13, F18 | Medium |
| S5 | PAnP Suspended Case (Art. 366 CPP) & Precautionary Measures | `Proc. 0804041-57.2022.8.20.5600` | F03, F05, F06, F10, F13, F18 | High |
| S6 | Presencial Hearing with Complex Intimations | `Proc. 0876503-58.2025.8.20.5001` | F03, F06, F10, F11, F18 | Medium |
| S7 | GAECO / Multi-Defendant Complex Fraud Case | `Proc. 0802487-75.2026.8.20.5300` | F03, F05, F06, F07, F10, F18 | Very High |
| S8 | Declining Jurisdiction & Nested PDF Structure | `Proc. 0844118-57.2025.8.20.5001` | F03, F05, F06, F10, F18 | High |
| S9 | e-SAJ/TJSP Imported Records with Vertical Margin Stamps | `Proc. 0806049-87.2024.8.20.5001` | F03, F05, F06, F10, F18 | High |

## Test Architecture
- **Runner:** `python -m pytest tests/` and dedicated runner `python tests/run_all_tests.py`.
- **Directory Layout:**
  - `tests/unit/`: Test individual modules (`test_pje_indexer.py`, `test_docx_generator.py`, `test_offline_engine.py`, `test_models.py`).
  - `tests/e2e/`:
    - `test_e2e_tier1_features.py`: Feature coverage (≥5 tests per feature).
    - `test_e2e_tier2_boundaries.py`: Boundary and corner cases (empty inputs, missing fields, malformed stamps, offline network isolation).
    - `test_e2e_tier3_cross_features.py`: Interaction between indexer, extraction engines, field edits, and DOCX generation.
    - `test_e2e_tier4_workloads.py`: Full opaque-box validation on the 9 reference cases comparing extracted data and DOCX structure to ground truth.
- **Coordination:** The E2E Testing Track will author and execute this suite, publishing `TEST_READY.md` upon completion.
