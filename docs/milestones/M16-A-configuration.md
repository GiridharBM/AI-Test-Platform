# Milestone 16-A — Configuration & Reproducibility

Status: **CLOSED — VERIFIED**

## Scope

M16-A establishes configuration management and dependency reproducibility for the AI Test Platform.

## Capabilities

### Centralized Configuration

- **Configuration module** — `backend/app/core/config.py` with all resource limits and detection thresholds
- **Environment variable overrides** — `ATP_*` prefix for deployment customization
- **Fail-loud validation** — invalid environment values fail at import time, never silently degrade
- **No secret logging** — configuration values are never logged

### Pinned Dependencies

- **Runtime dependencies** — `backend/requirements.txt` with exact-pinned versions (e.g., `fastapi==0.141.1`, `pydantic==2.13.4`)
- **Dev dependencies** — `backend/requirements-dev.txt` including test tooling (`pytest==9.1.1`, `httpx==0.28.1`)
- **Testrunner dependencies** — `pytest==9.1.1`, `coverage==7.16.1` in `docker/Dockerfile.testrunner`

### Pinned Base Images

| Image | Version | Purpose |
|---|---|---|
| `python` | 3.14.6-slim | Backend runtime |
| `docker` | 29.6.1-cli | Backend Docker CLI |
| `node` | 22.20.0-alpine | Frontend build |
| `nginx` | 1.28.0-alpine | Frontend runtime |
| `python` | 3.12.14-slim | Testrunner base |

### Python Version

- `.python-version` = 3.14
- CI uses 3.14.6
- Testrunner uses 3.12.14 (for pytest/coverage compatibility)

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ATP_WORKSPACE_DIR` | `backend/workspace` | Ingested projects storage |
| `ATP_BACKEND_HOST` | `127.0.0.1` | HTTP bind address |
| `ATP_BACKEND_PORT` | `8000` | HTTP bind port |
| `ATP_TESTRUNNER_IMAGE` | `ai-test-platform-testrunner` | Sandbox Docker image |
| `ATP_PIPELINE_STUCK_TIMEOUT_SECONDS` | `1800` | Pipeline recovery timeout |

## Verification

- All dependencies are exact-pinned and reproducible
- Environment variables are validated at import time
- Configuration values are never logged
- `.env.example` documents all available overrides
