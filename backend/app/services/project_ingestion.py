"""Project ingestion: workspace creation, upload persistence, local-path
registration, input validation and path-traversal prevention.

Security model (Milestone 2):
- Uploaded files are written ONLY inside workspace/<project-id>/source/.
- Relative paths supplied by clients are sanitized; any path containing "..",
  absolute components or drive prefixes is rejected.
- Local paths are accepted only for existing directories outside protected
  system locations; the original project is treated strictly READ-ONLY.
- No uploaded code is ever executed, imported or installed.
"""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from fastapi import HTTPException

from app.core import config
from app.models.project import ProjectMeta

_META_DIR = ".meta"
_SOURCE_DIR = "source"


class IngestionError(HTTPException):
    """Ingestion failures surfaced as API errors."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_relative_path(raw: str) -> str:
    """Sanitize a client-supplied relative file path.

    Returns a safe posix-style relative path. Raises IngestionError on
    traversal attempts or invalid input rather than silently rewriting them.
    """
    if not raw or not raw.strip():
        raise IngestionError(status_code=400, detail="Empty file path.")
    if "\x00" in raw:
        raise IngestionError(status_code=400, detail=f"Invalid characters in path: {raw!r}")
    if len(raw) > config.MAX_REL_PATH_LENGTH:
        raise IngestionError(status_code=400, detail="File path too long.")

    # Normalize separators and strip drive prefixes / leading slashes so the
    # result can never be absolute.
    cleaned = raw.replace("\\", "/").strip()
    if len(cleaned) > 1 and cleaned[1] == ":":
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/")

    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts:
        raise IngestionError(status_code=400, detail=f"Invalid file path: {raw!r}")
    if any(p == ".." for p in parts):
        raise IngestionError(
            status_code=400,
            detail=f"Path traversal rejected: {raw!r}",
        )
    if any(len(p) > 255 for p in parts):
        raise IngestionError(status_code=400, detail=f"Path component too long: {raw!r}")

    return str(PurePosixPath(*parts))


def derive_project_name(relative_paths: list[str]) -> str:
    """Derive a display name from uploaded relative paths.

    If all paths share a common first component that is itself a directory
    component of at least one path (typical browser folder uploads include
    the selected folder name), use it. Otherwise use a neutral fallback.
    The name is display-only and never used as a filesystem path.
    """
    if not relative_paths:
        return "uploaded-project"
    first = {p.split("/", 1)[0] for p in relative_paths}
    if len(first) == 1:
        candidate = next(iter(first))
        if any("/" in p for p in relative_paths):
            return candidate[:100]
    return "uploaded-project"


def project_dir(workspace: Path, project_id: str) -> Path:
    return workspace / project_id


def source_dir(workspace: Path, project_id: str) -> Path:
    return project_dir(workspace, project_id) / _SOURCE_DIR


def _write_meta(workspace: Path, meta: ProjectMeta) -> None:
    meta_path = project_dir(workspace, meta.project_id) / _META_DIR / "meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(meta.model_dump_json(), encoding="utf-8")


def read_meta(workspace: Path, project_id: str) -> ProjectMeta:
    meta_path = project_dir(workspace, project_id) / _META_DIR / "meta.json"
    if not meta_path.is_file():
        raise IngestionError(status_code=404, detail=f"Unknown project: {project_id}")
    return ProjectMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))


def save_profile(workspace: Path, profile_json: str) -> None:
    """Persist a generated profile under .meta/ (never inside scanned trees)."""
    # Caller supplies the project id via the JSON payload.
    pid = json.loads(profile_json)["project_id"]
    meta_path = project_dir(workspace, pid) / _META_DIR / "profile.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(profile_json, encoding="utf-8")


def read_profile(workspace: Path, project_id: str) -> str | None:
    profile_path = project_dir(workspace, project_id) / _META_DIR / "profile.json"
    if not profile_path.is_file():
        return None
    return profile_path.read_text(encoding="utf-8")


def save_codemap(workspace: Path, codemap_json: str) -> None:
    """Persist a generated code map under .meta/ (never inside scanned trees)."""
    pid = json.loads(codemap_json)["project_id"]
    meta_path = project_dir(workspace, pid) / _META_DIR / "codemap.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(codemap_json, encoding="utf-8")


def read_codemap(workspace: Path, project_id: str) -> str | None:
    codemap_path = project_dir(workspace, project_id) / _META_DIR / "codemap.json"
    if not codemap_path.is_file():
        return None
    return codemap_path.read_text(encoding="utf-8")


def save_test_plan(workspace: Path, plan_json: str) -> None:
    """Persist a generated test plan under .meta/ (never inside scanned trees)."""
    pid = json.loads(plan_json)["project_id"]
    meta_path = project_dir(workspace, pid) / _META_DIR / "test_plan.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(plan_json, encoding="utf-8")


def read_test_plan(workspace: Path, project_id: str) -> str | None:
    plan_path = project_dir(workspace, project_id) / _META_DIR / "test_plan.json"
    if not plan_path.is_file():
        return None
    return plan_path.read_text(encoding="utf-8")


def save_test_generation(workspace: Path, gen_json: str) -> None:
    """Persist generated test scaffolds metadata under .meta/."""
    pid = json.loads(gen_json)["project_id"]
    meta_path = project_dir(workspace, pid) / _META_DIR / "test_generation.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(gen_json, encoding="utf-8")


def read_test_generation(workspace: Path, project_id: str) -> str | None:
    gen_path = project_dir(workspace, project_id) / _META_DIR / "test_generation.json"
    if not gen_path.is_file():
        return None
    return gen_path.read_text(encoding="utf-8")


def save_upload(
    files: list[tuple[str, bytes]],
    workspace: Path | None = None,
) -> ProjectMeta:
    """Persist an uploaded folder, preserving relative directory structure.

    `files` is a list of (relative_path, content_bytes) pairs. Content is
    passed fully buffered by the API layer after per-file size checks.
    """
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    if len(files) > config.MAX_UPLOAD_FILES:
        raise IngestionError(
            status_code=413,
            detail=f"Too many files: {len(files)} (max {config.MAX_UPLOAD_FILES}).",
        )

    sanitized: list[tuple[str, bytes]] = []
    total = 0
    for rel, content in files:
        safe_rel = sanitize_relative_path(rel)
        size = len(content)
        if size > config.MAX_FILE_SIZE_BYTES:
            raise IngestionError(
                status_code=413,
                detail=f"File too large: {safe_rel} ({size} bytes, "
                       f"max {config.MAX_FILE_SIZE_BYTES}).",
            )
        total += size
        if total > config.MAX_TOTAL_SIZE_BYTES:
            raise IngestionError(
                status_code=413,
                detail=f"Total upload exceeds {config.MAX_TOTAL_SIZE_BYTES} bytes.",
            )
        sanitized.append((safe_rel, content))

    project_id = uuid.uuid4().hex
    dest_root = source_dir(ws, project_id).resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    try:
        for safe_rel, content in sanitized:
            final = (dest_root / safe_rel).resolve()
            # Defence in depth: even after sanitization, verify containment.
            if not final.is_relative_to(dest_root):
                raise IngestionError(
                    status_code=400,
                    detail=f"Resolved path escapes workspace: {safe_rel}",
                )
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_bytes(content)
    except Exception:
        # Never leave partial projects behind on failure.
        shutil.rmtree(project_dir(ws, project_id), ignore_errors=True)
        raise

    meta = ProjectMeta(
        project_id=project_id,
        name=derive_project_name([rel for rel, _ in sanitized]),
        origin="upload",
        file_count=len(sanitized),
        created_at=_now(),
    )
    _write_meta(ws, meta)
    return meta


def register_local_project(raw_path: str, workspace: Path | None = None) -> ProjectMeta:
    """Register an explicitly supplied local directory for READ-ONLY profiling.

    Validation rules:
    - path must exist and be a directory;
    - drive roots (e.g. C:\\) are rejected;
    - any path component matching a protected system directory name is rejected;
    - paths inside the platform workspace are rejected (self-analysis guard).

    Symlinks inside the project are NOT followed during scanning; resolving
    the user-supplied root itself is intentional (explicit user selection).
    """
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    try:
        resolved = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise IngestionError(
            status_code=400,
            detail=f"Path does not exist or cannot be resolved: {raw_path!r} ({exc})",
        ) from exc

    if not resolved.is_dir():
        raise IngestionError(status_code=400, detail=f"Not a directory: {resolved}")

    if len(resolved.parts) <= 1:
        raise IngestionError(
            status_code=400,
            detail="Refusing to analyze a filesystem/drive root.",
        )

    # Only check the first level under the drive/root. Protected system dirs
    # (Windows, Program Files) sit directly under the drive. Deep nesting
    # like C:\Users\girid\AppData\... is a legitimate user path.
    first_level = resolved.parts[1].casefold() if len(resolved.parts) > 1 else ""
    if first_level in {n.casefold() for n in config.PROTECTED_DIR_NAMES}:
        raise IngestionError(
            status_code=400,
            detail=f"Refusing protected/system location (matched: {first_level}).",
        )

    ws_resolved = ws.resolve()
    if resolved == ws_resolved or ws_resolved in resolved.parents:
        raise IngestionError(
            status_code=400,
            detail="Refusing to analyze a path inside the platform workspace.",
        )

    meta = ProjectMeta(
        project_id=uuid.uuid4().hex,
        name=resolved.name[:100],
        origin="path",
        source_path=str(resolved),
        created_at=_now(),
    )
    _write_meta(ws, meta)
    return meta
