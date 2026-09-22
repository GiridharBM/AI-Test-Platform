# AI Test Platform

A privacy-preserving, GPU-accelcelerated autonomous GenAI platform for automated software testing.

## Current Status

> **Milestone 16 — CLOSED — VERIFIED**
> Release: **v0.1.0** (published to GHCR)

The platform can ingest and profile projects, produce a structured code map, generate prioritised test plans, produce deterministic test scaffolds, and execute them in an isolated Docker sandbox. It diagnoses test failures deterministically, improves generated tests deterministically, verifies improvements via deterministic re-testing, and evaluates the testing pipeline: dynamic Python execution coverage, bounded mutation testing, and bounded CPU/GPU benchmarking, all run inside the Docker sandbox. The pipeline supports source-code repair with human approval, persistence and recovery, observability, and project discovery. All stages are deterministic and private. No source code is modified without approval. No AI inference is required. No external/cloud calls.

## Milestones

| Milestone | Status | Scope |
|---|---|---|
| M1–M6 | Implemented | Core autonomous testing pipeline: ingestion, profiling, code map, test planning, generation, execution |
| M7 | Implemented | Deterministic failure diagnosis with optional local/private AI boundary |
| M8 | Implemented | Deterministic test improvement (scaffold regeneration) |
| M9 | Implemented | Re-test verification (improved tests vs baseline) |
| M10 | Implemented | Evaluation: dynamic coverage, bounded mutation testing, CPU/GPU benchmarking |
| M11 | Implemented | Source-code repair with human approval |
| M14 | Implemented | Source resolution, results semantics, pipeline resume |
| M15 | Implemented | Persistence, recovery, observability, project discovery |
| M16 | **CLOSED — VERIFIED** | Configuration, containerization, CI, release machinery |
| M17 | **PLANNED** | NVIDIA DGX B200 deployment, GPU acceleration, AI inference |

## Long-Term Vision

The platform autonomously tests software projects through a continuous loop:

```
Analyze → Plan → Generate → Execute → Diagnose → Improve → Re-test → Evaluate
```

1. **Analyze** — repository-level code understanding via code-aware RAG
2. **Plan** — risk-based and requirements-based test planning
3. **Generate** — autonomous generation of unit, integration, API, edge-case, security-oriented, and regression tests
4. **Execute** — sandboxed test runs in Docker containers
5. **Diagnose** — AI-driven failure analysis and potential bug detection
6. **Improve** — test regeneration and sandboxed code repair (human approval required before modifying the original project)
7. **Re-test** — verify M8 improvements fixed diagnosed failures
8. **Evaluate** — coverage analysis, mutation testing, and CPU/GPU benchmarking

## Planned Technology Areas

These are planned, not yet implemented:

- **Frontend:** React, Vite, TypeScript, Tailwind CSS (current stack; planned Next.js dashboard for live agent activity)
- **Backend:** FastAPI, Python
- **AI/ML:** PyTorch, Hugging Face Transformers, open-source coding LLMs
- **Code intelligence:** Tree-sitter, code-aware RAG
- **Vector store:** Qdrant
- **Execution:** Docker sandboxed test execution
- **Acceleration:** NVIDIA GPU inference (local RTX 5060; NVIDIA DGX B200 for larger experiments — **PLANNED, M17**)
- **Language coverage:** Python, Java, JavaScript/TypeScript testing

## Development Principle

This project is implemented incrementally. Each milestone is verified before the next one begins. See [docs/architecture/architecture.md](docs/architecture/architecture.md) for the current architecture state.

## Repository Layout

```
frontend/    React/Vite/TypeScript dashboard
backend/     FastAPI application
docker/      Sandbox execution configs
benchmarks/  CPU/GPU benchmarking (future)
experiments/ Research experiments (future)
docs/        Architecture, deployment, release, milestones, audits
```

## Quick Start

### Local Development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000` for the project-ingestion UI, or use the API directly:

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Service health check |
| `/ready` | GET | Readiness gate (workspace + Docker) |
| `/api/projects/upload` | POST | Upload a project folder (multipart) |
| `/api/projects/from-path` | POST | Register a local directory for profiling |
| `/api/projects/{id}/profile` | POST | Run deterministic profiling |
| `/api/projects/{id}/discover` | POST | Run test discovery and build code map |
| `/api/projects/{id}/plan` | POST | Generate prioritised test plan |
| `/api/projects/{id}/generate` | POST | Generate deterministic test scaffolds |
| `/api/projects/{id}/execute` | POST | Execute tests in Docker sandbox |
| `/api/projects/{id}/diagnose` | POST | Run deterministic failure diagnosis |
| `/api/projects/{id}/improve` | POST | Improve failing generated tests deterministically |
| `/api/projects/{id}/retest` | POST | Re-test M8 improvements and compare against baseline |
| `/api/projects/{id}/evaluate` | POST | Run coverage, mutation, and benchmark evaluation |
| `/api/projects/{id}` | GET | Retrieve metadata, profile, code map, test plan, generated tests, execution, diagnosis, improvement, retest, and evaluation results |

Run tests:

```bash
pytest          # 752 tests — ingestion, profiling, discovery, planning, generation, execution, diagnosis, improvement, retest, evaluation, API, security
```

### Container Deployment (Docker Compose)

Full production topology for the whole platform (browser → nginx/SPA → FastAPI
backend → Docker socket → dynamic testrunner containers). Linux host is the
primary target; see [docs/deployment/deployment.md](docs/deployment/deployment.md) for Docker GID
setup, identical-path workspace requirements, and security notes.

```bash
# Pre-build the sandbox testrunner image, then the backend and frontend.
docker compose --profile testrunner build testrunner backend frontend

# Start the stack (frontend published on http://localhost:8080 by default).
docker compose up -d

# Verify.
docker compose ps
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

Notes:

- Only the frontend publishes a host port; the backend is reachable only via
  nginx. `/api/projects/from-path` is excluded at the proxy (bare-metal/local
  development API only).
- The backend requires the Docker socket for sandboxed execution; mounting it
  grants host-root-equivalent Docker control — restrict this deployment to a
  trusted host.
- The workspace is an identical-path bind mount at
  `/var/lib/ai-test-platform/workspace` (do not use a named volume).

### Published Images (v0.1.0)

| Image | Registry |
|---|---|
| `ghcr.io/giridharbm/ai-test-platform-backend:v0.1.0` | GHCR |
| `ghcr.io/giridharbm/ai-test-platform-frontend:v0.1.0` | GHCR |
| `ghcr.io/giridharbm/ai-test-platform-testrunner:v0.1.0` | GHCR |

See [docs/release/release.md](docs/release/release.md) for the release process.
See [docs/release/CHANGELOG.md](docs/release/CHANGELOG.md) for the changelog.

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture/architecture.md) | System architecture, all milestones |
| [Deployment](docs/deployment/deployment.md) | Docker Compose deployment guide |
| [Release](docs/release/release.md) | Release process and GHCR publishing |
| [CHANGELOG](docs/release/CHANGELOG.md) | Release history |
| [Security Model](docs/security/security-model.md) | Security boundaries and trust model |
| [Setup](docs/development/setup.md) | Development environment setup |
| [Testing](docs/development/testing.md) | Test suite guide |
| [Contributing](docs/development/CONTRIBUTING.md) | Contribution guidelines |

## Milestone Documentation

| Document | Description |
|---|---|
| [M15 — Persistence](docs/milestones/M15-persistence.md) | Persistence, recovery, observability |
| [M16-A — Configuration](docs/milestones/M16-A-configuration.md) | Configuration and reproducibility |
| [M16-B — Containerization](docs/milestones/M16-B-containerization.md) | Docker Compose topology |
| [M16-C — CI/Release](docs/milestones/M16-C-ci-release.md) | CI workflow and release machinery |
| [M17 — DGX B200](docs/milestones/M17-dgx-b200.md) | **PLANNED** — NVIDIA DGX B200 |

## License

MIT
