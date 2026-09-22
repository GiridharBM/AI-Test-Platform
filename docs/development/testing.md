# Testing Guide

## Backend Tests

```bash
cd backend
pytest
```

**Verified baseline:** 752 collected / 749 passed / 3 skipped / 0 failed

The 3 skipped tests are platform-specific (Windows-only skips on Linux CI).

Run a specific test:

```bash
pytest tests/test_health.py -v
```

Run with coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

## Frontend Tests

```bash
cd frontend
npx vitest run
```

Run in watch mode:

```bash
npx vitest
```

## Typecheck

```bash
cd frontend
npm run typecheck
```

## Production Build

```bash
cd frontend
npm run build
```

## CI-Equivalent Validation

To replicate the CI workflow locally:

```bash
# Backend
cd backend
python -m pytest -q

# Frontend
cd frontend
npx vitest run
npm run typecheck
npm run build

# Compose validation
docker compose --profile testrunner config -q

# Container build
docker compose --profile testrunner build testrunner backend frontend
```

## Test Structure

Backend tests are organized by feature:

| Test File | Coverage |
|---|---|
| `test_projects_api.py` | Project CRUD, upload, from-path |
| `test_pipeline.py` | Pipeline state machine |
| `test_execution.py` | Docker sandbox execution |
| `test_diagnosis.py` | Failure diagnosis |
| `test_improvement.py` | Test improvement |
| `test_retest.py` | Re-test verification |
| `test_evaluation.py` | Coverage, mutation, benchmark |
| `test_repair.py` | Source-code repair |
| `test_readiness.py` | Health/readiness endpoints |
| `test_config_env.py` | Environment variable configuration |
| `test_security.py` | Security boundary tests |

## Docker Sandbox Tests

Some tests require Docker. If Docker is unavailable, these tests are skipped or fail gracefully. The sandbox tests verify:

- Isolated pytest execution with `--network none`
- Read-only source mounting
- Resource limits (memory, CPU, timeout)
- Automatic cleanup
