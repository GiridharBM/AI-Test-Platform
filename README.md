# AI Test Platform

A privacy-preserving, GPU-accelerated autonomous GenAI platform for automated software testing.

## Current Status

> **Milestone 7 — Hybrid Failure Diagnosis**

The platform can ingest and profile projects, produce a structured code map, generate prioritised test plans, produce deterministic test scaffolds, and execute them in an isolated Docker sandbox. It now also diagnoses test failures deterministically: what failed, how it failed, its category, a stable failure signature, linked source locations from the code map, and severity — reporting `DiagnosisResult` with structured findings. An optional local/private AI boundary exists but is **off by default** and performs no external calls; no repair/regeneration is performed in this milestone.

## Long-Term Vision

The platform will autonomously test software projects through a continuous loop:

```
Analyze → Plan → Generate → Execute → Diagnose → Improve → Re-test → Evaluate
```

1. **Analyze** — repository-level code understanding via code-aware RAG
2. **Plan** — risk-based and requirements-based test planning
3. **Generate** — autonomous generation of unit, integration, API, edge-case, security-oriented, and regression tests
4. **Execute** — sandboxed test runs in Docker containers
5. **Diagnose** — AI-driven failure analysis and potential bug detection
6. **Improve** — test regeneration and sandboxed code repair (human approval required before modifying the original project)
7. **Re-test** — verify fixes and improved tests
8. **Evaluate** — coverage analysis, mutation testing, and CPU/GPU benchmarking

## Planned Technology Areas

These are planned, not yet implemented:

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Python
- **AI/ML:** PyTorch, Hugging Face Transformers, open-source coding LLMs
- **Code intelligence:** Tree-sitter, code-aware RAG
- **Vector store:** Qdrant
- **Execution:** Docker sandboxed test execution
- **Acceleration:** NVIDIA GPU inference (local RTX 5060; NVIDIA DGX B200 for larger experiments)
- **Language coverage:** Python, Java, JavaScript/TypeScript testing

## Development Principle

This project is implemented incrementally. Each milestone is verified before the next one begins. See [docs/architecture.md](docs/architecture.md) for the current architecture state.

## Repository Layout

```
frontend/    Future Next.js dashboard (not yet initialized)
backend/     FastAPI application
docker/      Sandbox execution configs (future)
benchmarks/  CPU/GPU benchmarking (future)
experiments/ Research experiments (future)
docs/        Architecture and project documentation
```

## Backend Quick Start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000` for the project-ingestion UI, or use the API directly:

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Service health check |
| `/api/projects/upload` | POST | Upload a project folder (multipart) |
| `/api/projects/from-path` | POST | Register a local directory for profiling |
| `/api/projects/{id}/profile` | POST | Run deterministic profiling |
| `/api/projects/{id}/discover` | POST | Run test discovery and build code map |
| `/api/projects/{id}/plan` | POST | Generate prioritised test plan |
| `/api/projects/{id}/generate` | POST | Generate deterministic test scaffolds |
| `/api/projects/{id}/execute` | POST | Execute tests in Docker sandbox |
| `/api/projects/{id}/diagnose` | POST | Run deterministic failure diagnosis |
| `/api/projects/{id}` | GET | Retrieve metadata, profile, code map, test plan, generated tests, execution, and diagnosis results |

Run tests:

```bash
pytest          # 281 tests — ingestion, profiling, discovery, planning, generation, execution, diagnosis, API, security
```

## Milestone 7 — Hybrid Failure Diagnosis

- **Deterministic diagnosis core** — parses M6 execution output, classifies failures (assertion, exception, import_error, timeout, collection_error, syntax_error, unknown), produces a stable SHA-256 failure signature, links failures to source locations via the code map, and derives deterministic severity. Fully testable without any model.
- **Optional local/private AI boundary** — a thin `analyze(context) -> PotentialBug | None` interface under `backend/app/agents/llm.py`. **Off by default** (`DIAGNOSIS_AI_ENABLED=False`). No external/cloud calls, no API keys, no LLM/GPU/RAG infrastructure — the AI stage belongs to a future milestone.
- **Structured results** — `DiagnosisResult` (`backend/app/models/diagnosis.py`) persisted to `.meta/diagnosis.json`, with `overall_status` of `no_failures` / `failures_diagnosed` / `no_execution`.
- **Read-only & private** — diagnosis never executes or imports project code, never sends source/test/stdout/stderr/tracebacks externally, and validates untrusted traceback paths so they can never address host files.
- **No repair yet** — diagnosis only reports; automated repair/regeneration belongs to the future Improve milestone.
