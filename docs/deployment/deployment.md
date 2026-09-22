# AI Test Platform — Container Deployment (M16-B)

## Overview

The M16-B milestone containerizes the whole platform into a single Docker
Compose stack. The production topology is:

```
Browser
   ↓  (http://<host>:8080)
┌────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────────┐
│ frontend   │   │ backend      │   │ Docker       │   │ testrunner        │
│ nginx/SPA  ├──►│ FastAPI      ├──►│ socket       ├──►│ containers        │
│ 80         │   │ 8000         │   │ /var/run/    │   │ (dynamic, sandbox)│
└────────────┘   └──────────────┘   └──────────────┘   └───────────────────┘
   /api/* → backend      workspace bind (identical path)
   /health → backend     /var/lib/ai-test-platform/workspace
   /ready → backend
```

Only the **frontend** is host-published. The backend listens on
`0.0.0.0:8000` inside the compose network but its port is **never** published
to the host.

## Prerequisites

- **Linux host (primary target)** with Docker Engine + Compose v2. Linux is
  the designated target; the identical-path workspace bind works natively.
- **Docker Desktop (macOS / Windows / WSL2)** also runs all Linux containers;
  see [Windows limitations](#windows-docker-desktop-limitations) below.
- Docker daemon reachable and healthy (`docker info` succeeds).
- Enough host space for images and the workspace.

## Docker installation

Standard Docker Engine (`docker-ce`) or Docker Desktop. Compose v2 is required
(`docker compose` subcommand). Confirm with:

```bash
docker version
docker compose version     # v2.x+
```

## Docker daemon requirement

The backend drives the sandbox runner (`docker info`, `docker image inspect`,
`docker build`, `docker run`) because test execution happens in dynamic
testrunner containers. The backend must therefore have a working Docker CLI
and socket access inside its container.

## ⚠ Docker socket security warning

The backend container mounts `/var/run/docker.sock`. **Access to the Docker
daemon socket is functionally equivalent to root on the host.** This is an
explicit, accepted M16-B tradeoff: it is how sandboxed test execution works
here. It does **not** provide ordinary container isolation *for callers of the
backend*. Practical consequences:

- Anyone able to reach the backend API can trigger container execution on the
  host daemon (the testrunner sandbox itself stays `--network none`,
  `--read-only`, tmpfs, resource-limited, non-root).
- Do **not** deploy this stack on an untrusted/shared host, and do **not**
  publish the backend port.
- A future hardened deployment (rootless/remote-TLS Docker, external runtime)
  belongs to M16-D; it is explicitly out of scope for this milestone.

## Host workspace requirement

Create the host workspace (paths are the documented default):

```bash
sudo mkdir -p /var/lib/ai-test-platform/workspace
```

### Identical host/container workspace path

The workspace **must** be a bind mount at the **same absolute path** on the
host and inside the backend container:

```yaml
volumes:
  - /var/lib/ai-test-platform/workspace:/var/lib/ai-test-platform/workspace
```

The backend creates temporary directories under the workspace
(`TMPDIR=/var/lib/ai-test-platform/workspace/.tmp`) that are later passed as
**absolute bind-mount paths to the host Docker daemon** (the `exec_*`/`eval_*`
mounts used by the sandbox runner). If host and container paths differed, the
host daemon could not resolve those mounts and execution would fail. A **named
Docker volume cannot satisfy this identity requirement** — use the bind mount.

The backend container entrypoint creates `/var/lib/ai-test-platform/workspace`
and `…/.tmp` and chowns them to the app user (UID 1000) on startup, so the
bind need not exist beforehand, but creating it operationally documents intent.

## Docker GID setup

The backend application runs **non-root** (UID 1000). To let it use the
mounted Docker socket, Compose adds the *host* Docker group's numeric GID as a
supplementary group. Docker Compose substitutes it from
`ATP_DOCKER_GID` (default `999`). On the **Docker host**, obtain the GID with
either:

```bash
getent group docker | cut -d: -f3
# or
stat -c '%g' /var/run/docker.sock
```

Then, in the file `.env` (not committed; see `.env.example`):

```
ATP_DOCKER_GID=<your-host-gid>
```

If the Docker socket's group differs (e.g. a custom Docker group), use that
GID. If `/ready` reports the Docker probe failing, this is the first thing to
check.

## Environment configuration

Copy `.env.example` to `.env` and adjust. Only the variables that matter for
the container deployment:

| Variable | Default | Meaning |
|---|---|---|
| `ATP_FRONTEND_PORT` | `8080` | Host-facing nginx/SPA port |
| `ATP_DOCKER_GID` | `999` | Host Docker group GID (see above) |
| `ATP_WORKSPACE_DIR` | `/var/lib/ai-test-platform/workspace` | Backend workspace (must match compose bind) |
| `ATP_BACKEND_HOST` | `0.0.0.0` | Internal-only bind inside compose network |
| `ATP_BACKEND_PORT` | `8000` | Internal backend port |
| `ATP_TESTRUNNER_IMAGE` | `ai-test-platform-testrunner` | Must match the compose testrunner image |
| `ATP_PIPELINE_STUCK_TIMEOUT_SECONDS` | `1800` | M16-A pipeline recovery timeout |

The backend does **not** load `.env` itself; uvicorn is launched with the
values from the compose `environment` block.

## Testrunner image build

The sandbox testrunner image is built **before** the backend starts, into the
shared daemon, using the frozen `docker/Dockerfile.testrunner` (unchanged from
M16-A — pinned `python:3.12.14-slim`, `pytest==9.1.1`, `coverage==7.16.1`).

```bash
docker compose --profile testrunner build testrunner
```

The `testrunner` service is build-only (`profiles: ["testrunner"]`,
`restart: "no"`); a normal `up` never starts it. If it was ever missing at
runtime, the backend's existing fallback (`runner.py _ensure_image`) can build
it from `/app/docker/Dockerfile.testrunner`, which the backend image contains.

## Compose config validation

```bash
docker compose config
```

This validates the merged configuration (including `.env` substitution)
without building or starting anything.

## Startup

```bash
# Optional: reset platform state (container-scoped).
docker compose down

# Build everything in order (testrunner first).
docker compose --profile testrunner build testrunner backend frontend

# Start the stack.
docker compose up -d

# Status.
docker compose ps
```

The frontend depends on the backend becoming `healthy` (its healthcheck is the
backend's `/ready`), so nginx only joins once the workspace and Docker runtime
are actually working.

## Shutdown / restart

```bash
docker compose down        # stop + remove containers (workspace bind untouched)
docker compose down -v     # DANGER: also removes named volumes; the workspace
                           # bind is NOT affected but state resets anyway
docker compose restart backend    # restart one service
```

Since the pipeline state lives on the bind-mounted workspace, projects,
`.meta` artifacts, and generated tests survive restarts and `down`/`up`.

## Persistence

Persistent state = the host bind directory
`/var/lib/ai-test-platform/workspace` (identical path inside the container).
Neither images nor containers hold workspace state. Nothing else is persisted.

## Health / readiness

- `GET /health` — liveness; always OK while the backend process is up.
- `GET /ready` — readiness gate: workspace exists & writable **and** the
  Docker runtime responds (`docker info`). Returns 503 until ready. This is
  what the backend container healthcheck and the compose dependency ordering
  use.

Both are proxied through nginx at the frontend port:
`http://localhost:8080/health` and `http://localhost:8080/ready`.

## from-path exclusion (M16-B security boundary)

`POST /api/projects/from-path` registers an existing filesystem directory for
read-only profiling. Inside the backend container, paths such as `/app`,
`/tmp`, or `/etc` **do exist** and would otherwise be registerable by an
unauthenticated caller reaching the frontend — enabling metadata/enumeration
of the backend container filesystem and (via repair) writes to writable dirs.

The production nginx config therefore **excludes the route before the generic
`/api/` proxy** (`frontend/nginx.conf`):

```nginx
location ~ ^/api/projects/from-path/?$ {
    return 404;
}
```

Consequences:

- **The containerized deployment does not expose from-path** — both
  `/api/projects/from-path` and `/api/projects/from-path/` return 404 at the
  proxy.
- **The frontend never calls this endpoint** (verified: no call sites).
- **Bare-metal/local development is unchanged** — the endpoint still exists in
  the backend and is reachable in direct (non-nginx) setups.
- Future access-control / directory-allowlist work belongs to **M16-D**.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `/ready` 503, Docker probe failing | `ATP_DOCKER_GID` wrong — re-check with `stat -c '%g' /var/run/docker.sock`; confirm socket mounted |
| Backend `unhealthy` on first up | Backend still init-ing; wait for `start_period`. If it stays unhealthy, `docker compose logs backend` |
| Execution errors on `-v` mounts | Workspace bind not at the identical path, or `TMPDIR` not under the workspace |
| `docker: permission denied` | Backend process group lacks the Docker GID — verify `group_add` + `.env` |
| Port conflict | Change `ATP_FRONTEND_PORT` |
| Container `docker build` fallback slow | Pre-build the testrunner image (see above) |

## Windows Docker Desktop limitations

- Windows itself is **not** a target; the Linux VM (WSL2) engine runs the
  containers, and recommended paths like `/var/lib/ai-test-platform/workspace`
  live inside the VM.
- Bind sources are auto-translated by Docker Desktop; keep the workspace on
  the VM-side path (as documented) for predictable behavior. A host `C:\…`
  path would not be resolvable by the backend's later `-v` mounts.
- `group_add` semantics and GID discovery behave as on a Linux host **inside
  the VM** (`docker run --rm alpine ls -ln /var/run/docker.sock` to inspect).

## Linux primary target

The recommended deployment is a Linux host with Docker Engine. All documented
commands assume Linux-style paths and permissions.

## Single-worker limitation

The stack runs **exactly one uvicorn worker**. The backend uses in-process
per-project locks and runs the pipeline inline during requests; multiple
workers would break concurrency guarantees. Horizontal scaling is out of scope
for M16-B.

## Known security boundary

- Docker socket in the backend container = host-root-equivalent Docker
  control (see the warning above). Intended for a trusted single-host alpha
  deployment.
- No authentication, no TLS, no CORS redesign in this milestone.
- The sandbox flags of the dynamic testrunner containers are unchanged:
  `--network none`, `--read-only`, `--tmpfs /tmp:size=64m`, memory/CPU limits,
  non-root runner, list-based subprocess (no shell).