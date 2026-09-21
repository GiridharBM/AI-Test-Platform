# AI Test Platform backend image (M16-B containerization).
#
# In-image layout mirrors the repository so existing repo-root-relative path
# resolution still holds: /app is the repo root, so the app code lives at
# /app/app/main.py and EXECUTION_DOCKERFILE (docker/Dockerfile.testrunner)
# resolves to /app/docker/Dockerfile.testrunner.
#
# Pinned base: python:3.14.6-slim == the M16-A verified runtime
# (backend/.python-version is 3.14; the M16-A venv measured CPython 3.14.6).

# --- Build stage: pinned Docker CLI (matches a current supported daemon) ----
FROM docker:29.6.1-cli AS docker-cli

# --- Runtime stage -----------------------------------------------------------
FROM python:3.14.6-slim AS runtime

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# util-linux provides `setpriv`, used to drop from the init (root) user to the
# non-root application user while retaining supplementary groups (the Docker
# socket group from compose group_add). passwd provides groupadd/useradd.
RUN apt-get update \
    && apt-get install -y --no-install-recommends util-linux passwd \
    && rm -rf /var/lib/apt/lists/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
# Bake the frozen testrunner Dockerfile at its expected in-image location so
# the existing runtime image-build fallback (runner.py _ensure_image) works.
COPY --from=testrunner Dockerfile.testrunner /app/docker/Dockerfile.testrunner

WORKDIR /app

# Install ONLY the runtime closure (M16-A requirements.txt). No dev deps.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Non-root application user, UID 1000 (M16-B requirement).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /app --shell /usr/sbin/nologin app

ENV ATP_WORKSPACE_DIR=/var/lib/ai-test-platform/workspace \
    ATP_BACKEND_HOST=0.0.0.0 \
    ATP_BACKEND_PORT=8000 \
    ATP_TESTRUNNER_IMAGE=ai-test-platform-testrunner \
    TMPDIR=/var/lib/ai-test-platform/workspace/.tmp

EXPOSE 8000

# Init as root: ensure the workspace + .tmp exist and are writable by the app
# user (bind mounts are created empty by Docker). Then drop to uid 1000
# (supplementary groups preserved, so compose group_add's Docker socket group
# survives) and exec uvicorn. The M16-A host/port variables are wired here —
# never hardcoded in application code.
CMD ["sh", "-c", "set -e; mkdir -p \"$ATP_WORKSPACE_DIR/.tmp\"; chown -R 1000:1000 \"$ATP_WORKSPACE_DIR\"; exec setpriv --reuid=1000 --regid=1000 --keep-groups --no-new-privs uvicorn app.main:app --host \"$ATP_BACKEND_HOST\" --port \"$ATP_BACKEND_PORT\""]