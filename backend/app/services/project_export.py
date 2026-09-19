"""Secure project export (Milestone 12).

Builds a bounded ZIP of an upload-origin project's authoritative workspace
source tree plus a PROJECT_EXPORT.json manifest. Read-only: project source,
.meta, repair and pipeline state are never mutated.

Security guarantees
-------------------
* The project resolves through the existing metadata mechanism (404 for
  unknown/traversal ids) and the source root is verified to be contained
  inside the platform workspace (realpath containment).
* Only upload-origin projects are exportable; path-origin is refused (400).
* Export is gated on pipeline ``overall_status == "completed"`` (409
  otherwise), so the archived source is always a terminal, consistent state.
* The walk never follows symlinks and never dereferences them: symlinked and
  non-regular files are skipped, and platform ignored directories are
  excluded. A root-level PROJECT_EXPORT.json in the source tree cannot
  clobber the platform manifest.
* The temporary ZIP lives in a dedicated temp directory removed after the
  response streams.
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from app.core import config
from app.models.pipeline import PIPELINE_COMPLETED, PipelineState
from app.models.repair import APPLICATION_NOT_APPLIED, RepairResult
from app.services import project_ingestion as ingestion

_MANIFEST_NAME = "PROJECT_EXPORT.json"
# Never export platform internals even if a nested dir shares the name.
_INTERNAL_DIRS = frozenset({".meta", "generated_tests"})


class ExportError(HTTPException):
    """Export failures surfaced as API errors."""


def _cleanup_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def cleanup_export_zip(zip_path: Path) -> None:
    """Remove a temporary export ZIP and its temp directory after streaming."""
    _cleanup_dir(zip_path.parent)


def build_project_zip(
    project_id: str,
    workspace: Optional[Path] = None,
) -> tuple[Path, str]:
    """Build a bounded export ZIP for a completed upload-origin project.

    Returns ``(zip_path, filename)`` where ``zip_path`` lives in a fresh temp
    directory (caller must clean it up, e.g. via ``cleanup_export_zip``).
    Raises ``ExportError`` for 400/404/409/500 conditions.
    """
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    meta = ingestion.read_meta(ws, project_id)  # 404 for unknown/traversal ids

    if meta.origin != "upload":
        raise ExportError(
            status_code=400,
            detail="Export is supported only for upload-origin projects.",
        )

    raw_pipeline = ingestion.read_pipeline(ws, project_id)
    if raw_pipeline is None:
        raise ExportError(
            status_code=409,
            detail="No pipeline state; export requires a completed pipeline.",
        )
    try:
        pipe = PipelineState.model_validate_json(raw_pipeline)
    except Exception:
        raise ExportError(status_code=500, detail="Project pipeline state is unreadable.")
    if pipe.overall_status != PIPELINE_COMPLETED:
        raise ExportError(
            status_code=409,
            detail=(
                f"Export requires overall_status='{PIPELINE_COMPLETED}' "
                f"(found '{pipe.overall_status}')."
            ),
        )

    source_root = ingestion.source_dir(ws, project_id)
    if not source_root.resolve().is_relative_to(Path(ws).resolve()):
        raise ExportError(
            status_code=400,
            detail="Project source escapes the platform workspace.",
        )
    if not source_root.is_dir():
        raise ExportError(status_code=404, detail="Project source is missing.")

    raw_repair = ingestion.read_repair(ws, project_id)
    repair_application_state = APPLICATION_NOT_APPLIED
    if raw_repair is not None:
        try:
            repair_application_state = RepairResult.model_validate_json(raw_repair).application_state
        except Exception:
            raise ExportError(status_code=500, detail="Project repair state is unreadable.")

    manifest = {
        "project_id": project_id,
        "origin": meta.origin,
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_overall_status": pipe.overall_status,
        "repair_application_state": repair_application_state,
    }

    filename = f"{project_id}-export.zip"
    tmp_dir = Path(tempfile.mkdtemp(prefix="export_"))
    zip_path = tmp_dir / filename

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(source_root, followlinks=False):
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in config.IGNORED_DIRS
                and d not in _INTERNAL_DIRS
                and not (Path(dirpath) / d).is_symlink()
            )
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.is_symlink() or not path.is_file():
                    continue
                rel_parts = os.path.relpath(dirpath, source_root)
                arc = name if rel_parts == "." else (
                    f"{Path(rel_parts).as_posix()}/{name}"
                )
                if arc == _MANIFEST_NAME:
                    continue  # reserved for the platform manifest below
                zf.write(path, arcname=arc)
        # Manifest last so it can never be shadowed by a source entry.
        zf.writestr(_MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n")

    return zip_path, filename