# AI Test Platform — Release Process (M16-C)

## Overview

Release publishing is handled by a single GitHub Actions workflow,
`.github/workflows/release.yml`. It is **tag-only** and **publish-only**: it
runs only when a `vMAJOR.MINOR.PATCH` tag is pushed, and it never modifies
the repository. Continuous integration is a separate workflow
(`ci.yml`); the Build phase of the roadmap is the release source of truth
for image builds.

Released artifacts are three container images published to GitHub Container
Registry (GHCR):

| Image | Contents |
|---|---|
| `ghcr.io/giridharbm/ai-test-platform-backend` | FastAPI backend (with bundled testrunner source) |
| `ghcr.io/giridharbm/ai-test-platform-frontend` | nginx/SPA frontend |
| `ghcr.io/giridharbm/ai-test-platform-testrunner` | Sandbox testrunner base image |

## Versioning

- The release version lives in the **`VERSION` file** at the repository root
  (plain `MAJOR.MINOR.PATCH`, no `v` prefix, trailing newline).
- A release is created by pushing a tag `vMAJOR.MINOR.PATCH` that **matches**
  the `VERSION` file exactly.
- The workflow validates this before doing anything else:
  - the tag must be exactly `v` + three dot-separated integer segments;
  - the `VERSION` file must be `MAJOR.MINOR.PATCH`;
  - tag and file must agree. Otherwise the job fails fast — no login, no
    build, no publish.

## Triggers

| Trigger | Effect |
|---|---|
| `git tag vX.Y.Z` + push | Runs the release workflow and publishes images |
| `push` to `main` (no tag) | `ci.yml` only — never publishes |
| `workflow_dispatch` | Not enabled in V1 (intentional; supply-chain narrowing) |
| `pull_request` | Never triggers release |

## How to release

Everything happens from an up-to-date, clean `main`:

```bash
# 1. Confirm VERSION matches the intended release.
cat VERSION            # e.g. 0.1.0

# 2. Tag the current HEAD and push the tag (this triggers the workflow).
git tag v0.1.0
git push origin v0.1.0
```

No other action is needed: the workflow builds and publishes the images.
The tag must point at the exact commit whose contents are being released
(the workflow checks out the tagged commit with full history).

## What the workflow does

1. **Check out the tagged commit** (full history; required for metadata).
2. **Validate the version** (see above).
3. **Set up Buildx** and **log in to GHCR** with the automatic
   `GITHUB_TOKEN` (repo-scoped; no personal token needed).
4. **Build all three images** (using the same sources Compose uses,
   including the `testrunner=docker` named build context for the backend).
   Nothing is published yet.
5. **Publish all three images** only if every build succeeded. This
   two-phase design eliminates partial releases: a failed backend build can
   never leave a half-published release.

Each image gets three tags:

| Tag | Meaning |
|---|---|
| `vX.Y.Z` | The release version |
| `sha-<12-char-git>` | The exact commit (immutable; useful for exact rollback) |
| `latest` | Convenience pointer to the most recent release |

The `latest` tag is produced **only** by this release workflow — the CI
workflow never publishes images, so `latest` always means "the most recent
tagged release."

## Publishing identity

- Registry: `ghcr.io`
- Owner/namespace: `giridharbm` (lowercase, must match the GHCR package
  owner exactly — GHCR namespaces are case-sensitive)
- Images carry OCI labels (`org.opencontainers.image.*`): title, version,
  commit revision, and source repo.

## Permissions and secrets

- The workflow uses **no user secrets**. Publishing uses the automatic
  `GITHUB_TOKEN` (available to workflows in this repository).
- Workflow-wide permissions are empty; the release job asks only for
  `contents: read` and `packages: write` — everything a publish needs,
  nothing more. No `id-token`, no `contents: write`.
- The ghcr.io registry needs the repo to be granted `Write` package access;
  by default, repositories under the same owner can publish.

## Deterministic reruns

A given tag always maps to the same commit, and the `sha-…` tag makes the
published artifact traceable to that exact commit. Rerunning a release for
the same tag re-publishes the same immutable tags (the version tags are
overwritten by the newer push).

## In-scope / out-of-scope (V1)

| Scope | V1 |
|---|---|
| CI (`ci.yml`, no publish) | ✔ |
| Tag-triggered release publishing | ✔ |
| GHCR publishing via repo token | ✔ |
| SBOM, OIDC federation, cosign/signing | Not in V1 |
| Manual/`workflow_dispatch` releases | Not in V1 |
| Pre-release / prerelease tags | Not in V1 |
| Multi-arch builds | Not in V1 |

## Verification

The release workflow reports back on the Actions tab of the repository
(`Actions` → `Release`). Success = both build and publish phases green for
all three images. Images can be inspected afterwards:

```bash
docker manifest inspect ghcr.io/giridharbm/ai-test-platform-backend:v0.1.0
```