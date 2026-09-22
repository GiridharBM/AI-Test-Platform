# M16-B Implementation — Containerization & Topology Final Verification Report

Checkpoint: `1611be5a4a2cb0f42266f7dbbbbd99f44b839c9d` (M16-A freeze).
Scope: Phase-2 authorized create/modify set only — created `backend/Dockerfile`,
`backend/.dockerignore`, `frontend/Dockerfile`, `frontend/nginx.conf`,
`frontend/.dockerignore`, `compose.yaml`, `docs/deployment.md`; modified
`.env.example`, `README.md`, `docs/architecture.md`. No M16-A file touched.
No commit, no push — independent audit follows. Repository tree is clean
(`git status --short` shows exactly the 11 intended files including this
report; `.env` and `backend/workspace` are git-ignored).

## 1. Approach

1. **Phase-1 design report** delivered (20 sections) before touching files.
2. **Security review** returned `CONSTRAINED`: `from-path` registers existing
   container-local dirs (`/app`, `/tmp`, `/etc` can register; workspace
   subtree, drive root `/`, protected Windows names rejected), no raw-content
   exfiltration endpoint, execution non-functional in-container (host daemon
   cannot resolve `-v` of container paths), repair-approve constrained.
   Required mitigation: exclude the route at the proxy.
3. **Phase-2 authorized** by follow-up prompt; implementation below.

## 2. Delivery

| File | Kind | Purpose |
|---|---|---|
| `backend/Dockerfile` | create | `python:3.14.6-slim` → `docker:29.6.1-cli` helper stage → runtime with `--from=docker-cli` docker binary, `util-linux`/`passwd` (setpriv), testrunner Dockerfile baked via compose `additional_contexts`, single-worker uvicorn. Root init (mkdir/chown workspace) then `setpriv --reuid=1000 --regid=1000 --keep-groups --no-new-privs` drop. |
| `backend/.dockerignore` | create | `workspace/`, `.venv`, tests, caches, Dockerfile. |
| `frontend/Dockerfile` | create | `node:22.20.0-alpine` → `npm ci` → `npm run build`; runtime `nginx:1.28.0-alpine`. |
| `frontend/nginx.conf` | create | `location ~ ^/api/projects/from-path/?$ { return 404; }` (before `/api/` proxy); `= /health`, `= /ready`; `/api/` → backend; SPA root + `try_files`; proxy headers. |
| `frontend/.dockerignore` | create | `node_modules/`, `dist/`, coverage, `.git`. |
| `compose.yaml` | create | `backend` (env, identical-path workspace bind both sides, `/var/run/docker.sock`, `group_add: ["${ATP_DOCKER_GID:-999}"]`, urllib healthcheck, no host port) + `frontend` (`${ATP_FRONTEND_PORT:-8080}:80`, `depends_on: service_healthy`, wget healthcheck) + `testrunner` (`profiles: ["testrunner"]`, context `docker`). |
| `docs/deployment.md` | create | operators doc: topology, prerequisites, Docker Desktop vs Linux, socket GID discovery (`getent group docker` / `stat -c '%g'`), from-path exclusion, workspace persistence, Windows limitations, troubleshooting. |
| `.env.example` | modify | M16-B block added next to M16-A entries. |
| `README.md` | modify | "Container Deployment (Docker Compose)" quick start. |
| `docs/architecture.md` | modify | "Milestone 16-B — Containerization & Topology" topology subsection. |

## 3. Design decisions

- **Pinned base image tags** (Docker Hub API-verified): `python:3.14.6-slim`
  (matches host venv 3.14.6), `docker:29.6.1-cli` (matches host engine),
  `node:22.20.0-alpine`, `nginx:1.28.0-alpine`. No floating `latest`.
- **Identical-path workspace bind** (`/var/lib/ai-test-platform/workspace`
  both sides): `runner.py` mount resolution works unchanged — `exec_*`/`eval_*`
  temp-relative paths exist identically in host and container.
- **Testrunner Dockerfile baked in**: compose `additional_contexts:
  { testrunner: docker }` + `COPY --from=testrunner Dockerfile.testrunner
  /app/docker/Dockerfile.testrunner` avoids root-context `.dockerignore` and
  keeps `EXECUTION_DOCKERFILE=/app/docker/Dockerfile.testrunner` valid.
- **setpriv with `--keep-groups`**: dropping to uid 1000 with `--no-new-privs`
  while retaining the compose `group_add` supplementary group (socket GID, 0 on
  this Docker Desktop; `999` documented as Linux default).
- **No host port for backend**; only nginx (8080) is published. `/health` and
  `/ready` re-exposed on the proxy so the browser cycle can use them.

## 4. Security enforcement

1. **from-path inert at the edge**: nginx regex location returns 404 before the
   `/api/` proxy, exact and trailing-slash forms verified live
   (`POST /api/projects/from-path` and `/from-path/` → 404, body served by
   `nginx/1.28.0`).
2. **Backend not host-published**: `docker compose ps` shows `8000/tcp`
   internal only; only `0.0.0.0:8080->80` is mapped (frontend).
3. **Socket in backend only**: compose mounts `/var/run/docker.sock` solely on
   the backend service.
4. **Sandbox argv untouched**: `backend/app/execution/runner.py` untouched
   (frozen checkbox); running images still mount `--read-only` + source `:ro`
   — proven by the live run's `PytestCacheWarning: Read-only file system` and
   `/source/calc.py` imports.
5. **Non-root verified**: PID 1 in the backend container is `uvicorn`, real
   UID/GID 1000 (`/proc/1/status` Uid: 1000×4); `setpriv --keep-groups` retains
   the supplementary Docker group needed for socket egress (socket probe
   `srw-rw---- root:root`, GID 0 group_add on this host).

## 5. Acceptance evidence (live)

1. `docker compose config --quiet` → OK (from-path / socket / groups / `ATP_`
   vars inspected).
2. All three images build with pinned bases; verified contents
   (`/app/app/main.py`, `/app/docker/Dockerfile.testrunner`, docker CLI
   29.6.1, setpriv; nginx conf contains the from-path block).
3. `docker compose up -d` → backend `(healthy)`, frontend `(healthy)`.
4. `GET :8080/health` → 200 `{"status":"ok","service":"ai-test-platform"}`;
   `GET :8080/ready` → 200 (both through nginx).
5. `GET :8080/` → 200, Vite SPA (`index-Bk6J_j6T.js` — hash matches the
   frontend `npm run build` output; not the backend placeholder).
6. `GET :8080/api/projects` → 200 same-origin proxy.
7. from-path boundary → 404 (both slash forms, nginx body).
8. **Sandbox E2E**: upload `calc.py` → full pipeline ran
   `upload→profile→discover→plan→generate→execute→diagnose→improve→execute→
   diagnose→improve(exhausted)→awaiting_retest_decision`. The real testrunner
   container ran 6 generated tests via the socket from inside the backend
   container; identical-path mounts resolved (`/source/calc.py`), sandbox
   flags intact. Failure is the expected M10 behavior (unfixable edge-case
   scaffolds), not a topology fault.
9. **Persistence**: project survives `docker compose restart backend` and a
   full `docker compose down` + `up -d` (bind-mounted workspace).

## 6. Regression (baseline parity)

| Gate | Command | Result | Baseline |
|---|---|---|---|
| Backend suite | `backend/.venv python -m pytest -q` | 749 passed, 3 skipped | 749 passed, 3 skipped |
| Frontend suite | `npx vitest run` | 283 passed (26 files) | 283 passed |
| Typecheck | `npm run typecheck` | clean | clean |
| Build | `npm run build` | built | built |

## 7. Troubleshooting encountered

- **Flaky registry DNS inside Docker Desktop VM** ("no such host" / "no HTTPS
  proxy"). Pre-pulled each pinned base with retry; BuildKit then resolved bases
  from the local store and the builds completed.
- **`setpriv` group flag required**: first CMD used bare
  `--reuid/--regid`; `setpriv` rejects it (`--[re]gid requires
  --keep-groups/--clear-groups/--init-groups/--groups`). Fixed with
  `--keep-groups` — which is exactly the semantics wanted (retain the
  supplementary Docker group). One-line change, rebuilt the backend image only.

## 8. Out of scope (unchanged by design)

- M16-A frozen files (runner, pipeline, ingestion, profiler, discovery,
  readiness, main, config, requirements, `.python-version`,
  `docker/Dockerfile.testrunner`, all `frontend/src/**`, package files).
- Sandbox argv, execution semantics, pipeline state machine.
- Multi-architecture builds, CI wiring, image registry pushing,
  secrets/vault integration, Kubernetes/alternate orchestration.

No commits or pushes were made. The stack is left running
(`docker compose --profile testrunner build testrunner backend frontend` +
`up -d`) for audit; tear-down: `docker compose down`.