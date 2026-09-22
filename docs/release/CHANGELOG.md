# Changelog

All notable changes to the AI Test Platform will be documented in this file.

## v0.1.0 — First Release

Release: v0.1.0
Tag: v0.1.0
Status: Released and verified

### Autonomous Testing Pipeline

- **M1–M6:** Core autonomous testing pipeline — ingestion, profiling, code map, test planning, generation, sandboxed execution
- **M7:** Deterministic failure diagnosis with optional local/private AI boundary
- **M8:** Deterministic test improvement (scaffold regeneration)
- **M9:** Re-test verification (improved tests vs baseline)
- **M10:** Evaluation — dynamic Python execution coverage, bounded mutation testing, bounded CPU/GPU benchmarking
- **M11:** Source-code repair with human approval

### Infrastructure

- **M14:** Source resolution, results semantics, pipeline resume
- **M15:** Persistence, recovery, observability, project discovery
- **M16-A:** Configuration and reproducibility — pinned dependencies, environment variables
- **M16-B:** Containerization — Docker Compose topology (nginx → FastAPI → Docker socket → testrunner)
- **M16-C:** CI and release machinery — GitHub Actions CI, GHCR publishing

### Published Images

| Image | Tag |
|---|---|
| `ghcr.io/giridharbm/ai-test-platform-backend` | v0.1.0 |
| `ghcr.io/giridharbm/ai-test-platform-frontend` | v0.1.0 |
| `ghcr.io/giridharbm/ai-test-platform-testrunner` | v0.1.0 |

### Known Limitations

- Single uvicorn worker (no horizontal scaling)
- No authentication/authorization
- No TLS/CORS redesign
- Docker socket access is host-root-equivalent
- Python-only evaluation (no Java/JS/TS)
- No LLM inference or AI model serving
- No GPU acceleration (planned for M17)
