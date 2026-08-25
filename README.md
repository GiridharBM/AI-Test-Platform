# AI Test Platform

A privacy-preserving, GPU-accelerated autonomous GenAI platform for automated software testing.

## Current Status

> **Milestone 3 — Code Map & Test Discovery**

The platform can now ingest and profile projects, and additionally produce a structured code map: per-file Python ast analysis (functions, classes, methods, signatures, decorators), test function discovery, heuristic test-to-source mapping, and testable target coverage summary.

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
| `/api/projects/{id}` | GET | Retrieve metadata, profile, and code map |

Run tests:

```bash
pytest          # 93 tests — upload, profiling, discovery, API, security
```
