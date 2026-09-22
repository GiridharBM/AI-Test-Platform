# Milestone 16-C — CI & Release Machinery

Status: **CLOSED — VERIFIED**

## Scope

M16-C establishes continuous integration and release machinery for the AI Test Platform.

## CI Workflow

**File:** `.github/workflows/ci.yml`
**Trigger:** `pull_request` + `push` to `main`
**Concurrency:** cancel-in-progress per ref

### Jobs

| Job | Purpose | Timeout |
|---|---|---|
| `backend-tests` | Python test suite | 30 min |
| `frontend-ci` | Vitest + typecheck + build | 20 min |
| `compose-validation` | Docker Compose config check | 10 min |
| `container-build` | Build all images + sanity check | 40 min |

### Backend Tests

```bash
python -m pytest -q
```

**Verified baseline:** 752 collected / 749 passed / 3 skipped / 0 failed

- Uses `python -m pytest` (not bare `pytest`) to avoid `ModuleNotFoundError`
- Python 3.14.6, pip cache on `requirements*.txt`

### Frontend CI

```bash
npx vitest run          # tests
npm run typecheck       # TypeScript
npm run build           # production build
```

- Node.js 22.20.0, npm cache on `package-lock.json`

### Compose Validation

```bash
docker compose --profile testrunner config -q
```

### Container Build

```bash
docker compose --profile testrunner build testrunner backend frontend
docker run --rm --entrypoint python ai-test-platform-backend -c "import app.main"
```

- Builds all three images (testrunner, backend, frontend)
- Sanity check verifies backend imports correctly

### Job Dependencies

```
backend-tests ─┐
frontend-ci ───┼──→ container-build
compose-validation ─┘
```

`container-build` only runs after all three test/validation jobs pass.

### Actions Pinning

All GitHub Actions are pinned to commit SHAs:

- `actions/checkout` → v4
- `actions/setup-python` → v5
- `actions/setup-node` → v4
- `docker/setup-buildx-action` → v3

### Permissions

- Top-level: `permissions: {}` (empty)
- Each job: `contents: read` only

## Release Workflow

**File:** `.github/workflows/release.yml`
**Trigger:** `push` tags `v*` only

### Process

1. Validate tag matches VERSION file
2. Set up Buildx + login to GHCR
3. Build all three images (no publish yet)
4. Publish all three images only if all builds succeed

### Published Images

| Image | Tags |
|---|---|
| `ghcr.io/giridharbm/ai-test-platform-backend` | `v0.1.0`, `sha-<12>`, `latest` |
| `ghcr.io/giridharbm/ai-test-platform-frontend` | `v0.1.0`, `sha-<12>`, `latest` |
| `ghcr.io/giridharbm/ai-test-platform-testrunner` | `v0.1.0`, `sha-12>`, `latest` |

### Permissions

- `contents: read`
- `packages: write`
- Uses automatic `GITHUB_TOKEN` (no user secrets)

### Version Validation

```bash
TAG_VER="${GITHUB_REF_NAME#v}"
FILE_VER="$(tr -d '[:space:]' < VERSION)"
# Must match exactly
```

## Verified Evidence

### Final CI Run

- **Run ID:** 35690336923
- **Commit:** `1b092c3106ff955732b50e60fb3afbeef6c3849a`
- **Status:** SUCCESS
- **Jobs:** All 4 PASS (backend-tests, frontend-ci, compose-validation, container-build)

### Release Run

- **Run ID:** 35621433418
- **Tag:** v0.1.0
- **Commit:** `c6fd64ffdc9314fa8ee8bb35913eb77df15d32b0`
- **Status:** SUCCESS

### Published Images (v0.1.0)

All three images verified on GHCR via `docker manifest inspect`.
