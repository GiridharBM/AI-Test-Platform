# Backend — AI Test Platform

FastAPI backend for the AI Test Platform.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
pip install -r requirements-dev.txt
```

- Supported Python: 3.14 (see `.python-version`; the test suite is verified
  against 3.14.6).
- Runtime-only deployments can install `requirements.txt` alone; developers
  and CI install `requirements-dev.txt` (runtime + pytest/httpx) and verify
  the resolved environment with `pip check`.

## Run

```bash
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`
Readiness: `GET http://localhost:8000/ready`

## Test

```bash
pytest          # 752 collected — ingestion, profiling, discovery, planning,
                # generation, execution, diagnosis, improvement, retest,
                # evaluation, API, security, source repair
```

Verified baseline: 752 collected / 749 passed / 3 skipped / 0 failed.

## Layout

- `app/main.py` — FastAPI application entry point, `/health`, `/ready` endpoints
- `app/api/` — API routers (projects, retest, evaluate)
- `app/agents/` — deterministic failure diagnosis + optional local/private AI boundary (M7)
- `app/code_intelligence/` — parsing and code understanding (future)
- `app/evaluation/` — dynamic coverage, bounded mutation testing, CPU/GPU benchmark, and evaluation orchestrator (M10)
- `app/execution/` — sandboxed test execution (M6), Docker runner
- `app/models/` — data models/schemas, including failure diagnosis (M7), test improvement (M8), re-test verification (M9), and pipeline evaluation (M10)
- `app/services/` — business logic, including:
  - deterministic test improvement (M8)
  - re-test verification (M9)
  - evaluation persistence (M10)
  - source-code repair with human approval (M11)
  - persistence, recovery, pipeline state management (M15)
  - project discovery and observability
- `app/core/config.py` — configuration; a few deployment values are overridable via `ATP_*` environment variables (see root `.env.example`): `ATP_WORKSPACE_DIR`, `ATP_BACKEND_HOST`, `ATP_BACKEND_PORT`, `ATP_PIPELINE_STUCK_TIMEOUT_SECONDS`, `ATP_TESTRUNNER_IMAGE`. Invalid overrides fail loudly at import; none are logged.
- `tests/` — pytest suite (752 tests)

## Key Milestones in Backend

- **M7** — Deterministic failure diagnosis with optional AI boundary
- **M8** — Deterministic test improvement (scaffold regeneration)
- **M9** — Re-test verification
- **M10** — Evaluation (coverage, mutation, benchmark)
- **M11** — Source-code repair with human approval
- **M14** — Source resolution, results semantics, pipeline resume
- **M15** — Persistence, recovery, observability, project discovery
- **M16** — Configuration, containerization, CI, release machinery

## Configuration

Configuration is centralized in `app/core/config.py`. Environment variables use the `ATP_` prefix. Invalid values fail at import time. Configuration values are never logged.

See `.env.example` for all available overrides.
