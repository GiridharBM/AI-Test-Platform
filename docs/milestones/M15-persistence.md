# Milestone 15 — Persistence, Recovery, Observability

Status: **Implemented**

## Scope

M15 adds persistence, recovery, observability, and project discovery to the autonomous testing pipeline.

## Capabilities

### Persistence

- **Atomic JSON writes** — all `.meta/` persistence uses atomic write patterns (write to temp file, then rename)
- **Project metadata** — profile, code map, test plan, generated tests, execution results, diagnosis, improvement, retest, evaluation all persisted under `.meta/`
- **Workspace persistence** — ingested projects and generated tests survive container restarts via bind-mounted workspace

### Recovery

- **Pipeline stuck detection** — pipelines left in `running` state beyond `ATP_PIPELINE_STUCK_TIMEOUT_SECONDS` (default 1800s) are automatically recovered to `unavailable`
- **Stale result handling** — orphaned execution/diagnosis/improvement results are cleaned up on recovery
- **Pipeline resume** — failed/unavailable pipelines can be resumed via `POST /api/projects/{id}/pipeline/resume`

### Observability

- **Readiness endpoint** — `GET /ready` reports workspace and Docker runtime status
- **Health endpoint** — `GET /health` returns service health
- **Structured logging** — application events logged with structured fields

### Project Discovery

- **Automatic discovery** — projects in the workspace directory are automatically discovered
- **Project listing** — `GET /api/projects` returns all discovered projects with their pipeline status

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ATP_PIPELINE_STUCK_TIMEOUT_SECONDS` | `1800` | Seconds before a running pipeline is considered stuck |

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/projects` | GET | List all projects |
| `/api/projects/{id}` | GET | Get project details (includes persistence state) |
| `/api/projects/{id}/pipeline/resume` | POST | Resume a failed/unavailable pipeline |
| `/ready` | GET | Readiness check (workspace + Docker) |

## Implementation Notes

- Persistence is filesystem-based (no database)
- Recovery is deterministic and idempotent
- No external services required (no Redis, no message queue)
- Pipeline state transitions are logged for observability
