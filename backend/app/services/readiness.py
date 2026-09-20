"""Readiness checks for GET /ready (O2).

Deterministic, bounded, machine-readable local prerequisites:
- workspace: the configured workspace directory exists and is writable
  (the application must be able to persist uploads and .meta state);
- runtime: the Docker runtime the test pipeline depends on is reachable.

Each check returns a plain boolean; the combined report never leaks paths,
details, or raw probe output. The docker probe is resolved lazily so tests
can monkeypatch it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from app.core import config


def workspace_available(workspace: Path | None = None) -> bool:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    return ws.is_dir()


def workspace_writable(workspace: Path | None = None) -> bool:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    probe = ws / f".ready-probe-{os.getpid()}"
    try:
        with open(probe, "w", encoding="utf-8"):
            pass
    except OSError:
        return False
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return True


def _runtime_available(docker_probe: Callable[[], tuple[bool, str]] | None) -> bool:
    probe: Callable[[], tuple[bool, str]]
    if docker_probe is not None:
        probe = docker_probe
    else:
        from app.execution.runner import _docker_probe as probe
    try:
        ok, _ = probe()
    except Exception:
        return False
    return bool(ok)


def check_readiness(
    workspace: Path | None = None,
    docker_probe: Callable[[], tuple[bool, str]] | None = None,
) -> dict:
    """Return a machine-readable readiness report dict.

    ``docker_probe`` is injectable for deterministic tests; defaults to the
    canonical runner probe (bounded, never raises).
    """
    ws_ok = workspace_available(workspace)
    wr_ok = workspace_writable(workspace) if ws_ok else False
    runtime_ok = _runtime_available(docker_probe)
    ready = ws_ok and wr_ok and runtime_ok
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {"workspace": ws_ok and wr_ok, "runtime": runtime_ok},
    }