# Security Model

## Overview

The AI Test Platform implements a layered security model. This document describes the verified current security boundaries.

## Trust Boundaries

### 1. Backend Container

- **Non-root execution** — UID 1000, `setpriv --keep-groups --no-new-privs`
- **Docker socket access** — mounted from host, grants host-root-equivalent Docker control
- **Single worker** — one uvicorn worker, no multi-process concerns
- **No authentication** — all endpoints are accessible to anyone who can reach the backend

**Risk:** Docker socket access is functionally equivalent to root on the host. This is an explicit, accepted tradeoff for sandboxed test execution.

### 2. Frontend/nginx Boundary

- **Host-published port** — only nginx (8080) is exposed to the host
- **Backend not published** — port 8000 is internal to the compose network
- **from-path exclusion** — `POST /api/projects/from-path` returns 404 at the proxy
- **SPA serving** — static files only, no server-side rendering

### 3. Testrunner Isolation

- **Docker sandbox** — each test execution runs in a fresh container
- **Network isolation** — `--network none`
- **Read-only filesystem** — `--read-only` with tmpfs for `/tmp`
- **Resource limits** — `--memory`, `--cpus`, timeout, output cap
- **Non-root runner** — `runner` user inside the container
- **Automatic cleanup** — `--rm` flag, temp directories removed

### 4. Source Code Protection

- **Read-only source mount** — source is copied and mounted `:ro` in the sandbox
- **No host execution** — project code never runs on the host
- **No source modification** — original source is never written to (except M11 repair with human approval)
- **Path traversal prevention** — validated path resolution, protected-dir rejection

## Configuration Security

- **No secrets in code** — `.env` is gitignored, `.env.example` has no real credentials
- **Fail-loud validation** — invalid configuration fails at import time
- **No secret logging** — configuration values are never logged
- **GITHUB_TOKEN only** — CI/CD uses automatic token, no personal tokens

## CI/CD Security

- **Minimal permissions** — `contents: read` for CI, `packages: write` for release
- **Pinned actions** — all GitHub Actions pinned to commit SHAs
- **No workflow_dispatch** — release is tag-triggered only
- **Build-before-publish** — all images built successfully before any publish

## Known Limitations

- **No authentication** — anyone with network access can use the API
- **No TLS** — traffic is unencrypted (deploy behind a reverse proxy for production)
- **No CORS redesign** — defaults apply
- **Docker socket = root** — backend container has host-root-equivalent access
- **Single-host only** — no distributed deployment support

## Security Recommendations

For production deployment:

1. Deploy behind a reverse proxy with TLS
2. Add authentication/authorization
3. Restrict network access to the backend
4. Monitor Docker socket usage
5. Use rootless Docker if possible (M16-D scope)
