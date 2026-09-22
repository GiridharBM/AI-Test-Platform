# Development Setup

## Prerequisites

- **Python 3.14** (see `backend/.python-version`)
- **Node.js 22** (see `frontend/package.json`)
- **Docker** (for sandboxed test execution)
- **Git**

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
pip install -r requirements-dev.txt
```

Verify the environment:

```bash
pip check
python -c "import app.main; print('OK')"
```

Run the backend:

```bash
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`
Readiness: `GET http://localhost:8000/ready`

## Frontend Setup

```bash
cd frontend
npm ci
npm run dev
```

The frontend dev server runs at `http://localhost:5173` by default.

Build for production:

```bash
npm run build
```

## Environment Configuration

Copy `.env.example` to `.env` and adjust as needed. All variables are optional; defaults are documented in `.env.example`.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `ATP_WORKSPACE_DIR` | `backend/workspace` | Where ingested projects are stored |
| `ATP_BACKEND_HOST` | `127.0.0.1` | HTTP bind address |
| `ATP_BACKEND_PORT` | `8000` | HTTP bind port |
| `ATP_TESTRUNNER_IMAGE` | `ai-test-platform-testrunner` | Docker image for sandbox execution |
| `ATP_PIPELINE_STUCK_TIMEOUT_SECONDS` | `1800` | Pipeline recovery timeout |

The backend does **not** load `.env` itself; it reads `ATP_*` environment variables directly.

## Docker/Compose Development Path

For containerized development:

```bash
# Build all images
docker compose --profile testrunner build testrunner backend frontend

# Start the stack
docker compose up -d

# Verify
docker compose ps
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

See [../deployment/deployment.md](../deployment/deployment.md) for full deployment documentation.

## Running Tests

See [testing.md](testing.md) for the complete test guide.
