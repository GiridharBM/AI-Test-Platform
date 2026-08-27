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
- `app/api/` — API routers (future)
- `app/agents/` — deterministic failure diagnosis + optional local/private AI boundary (M7)
- `app/code_intelligence/` — parsing and code understanding (future)
- `app/execution/` — sandboxed test execution (M6)
- `app/evaluation/` — coverage, mutation testing, benchmarks (future)
- `app/models/` — data models/schemas (future)
- `app/services/` — business logic (future)
- `tests/` — pytest suite
