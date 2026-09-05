# Backend — AI Test Platform

FastAPI backend for the AI Test Platform.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`

## Test

```bash
pytest
```

## Layout

- `app/main.py` — FastAPI application entry point
- `app/api/` — API routers (projects, retest, evaluate)
- `app/agents/` — deterministic failure diagnosis + optional local/private AI boundary (M7)
- `app/code_intelligence/` — parsing and code understanding (future)
- `app/execution/` — sandboxed test execution (M6)
- `app/evaluation/` — dynamic coverage, bounded mutation testing, CPU/GPU benchmark, and evaluation orchestrator (M10)
- `app/models/` — data models/schemas, including failure diagnosis (M7), test improvement (M8), re-test verification (M9), and pipeline evaluation (M10)
- `app/services/` — business logic, including deterministic test improvement (M8), re-test verification (M9), and evaluation persistence (M10)
- `tests/` — pytest suite (479 tests)
