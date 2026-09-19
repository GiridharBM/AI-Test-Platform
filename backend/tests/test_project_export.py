"""M12 secure project export tests (service + API)."""

import io
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.pipeline import PipelineState
from app.models.project import ProjectMeta
from app.models.repair import RepairResult
from app.services import project_export
from app.services.project_export import ExportError


def _now():
    return datetime.now(timezone.utc)


def _write_project(
    ws,
    pid,
    *,
    origin="upload",
    status="completed",
    files=None,
    repair_state=None,
    source_path=None,
):
    """Create a project directly in the workspace with meta/source attrs.

    `status` == None means no pipeline.json is written (not started).
    """
    src = ws / pid / "source"
    src.mkdir(parents=True, exist_ok=True) if origin == "upload" else None
    if files is None:
        files = {"calc.py": "def add(a, b):\n    return a + b\n"}
    for rel, content in files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    meta = ProjectMeta(
        project_id=pid, name=pid, origin=origin,
        source_path=source_path,
        file_count=len(files or []),
        created_at=_now(),
    )
    meta_path = ws / pid / ".meta" / "meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(meta.model_dump_json(), encoding="utf-8")

    if status is not None:
        pipe = PipelineState(
            project_id=pid, pipeline_id=pid,
            current_stage="completed" if status == "completed" else "running",
            overall_status=status,
        )
        pipe_path = ws / pid / ".meta" / "pipeline.json"
        pipe_path.write_text(pipe.model_dump_json(), encoding="utf-8")

    if repair_state is not None:
        r = RepairResult(project_id=pid, created_at=_now(), status="applied")
        r.application_state = repair_state
        repair_path = ws / pid / ".meta" / "repair.json"
        repair_path.write_text(r.model_dump_json(), encoding="utf-8")
    return pid


def _export(client, pid):
    return client.get(f"/api/projects/{pid}/export")


def test_completed_upload_origin_exports_valid_zip(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(
        ws, "proj1",
        files={
            "calc.py": "def add(a, b):\n    return a + b\n",
            "sub/util.py": "def two():\n    return 2\n",
            ".env": "SECRET=local\n",
            "README.md": "# demo\n",
        },
        repair_state="applied",
    )
    res = _export(client, pid)
    assert res.status_code == 200

    # Content-Type (required #8)
    assert res.headers["content-type"] == "application/zip"

    # Content-Disposition filename (required #9)
    assert f'filename="{pid}-export.zip"' in res.headers["content-disposition"]

    # Valid ZIP (required #2)
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = zf.namelist()

    # Source files included (required #3)
    assert "calc.py" in names
    assert "sub/util.py" in names

    # Dotfiles that belong to source preserved (required #21)
    assert ".env" in names
    assert "README.md" in names

    # Manifest exists (required #4)
    assert "PROJECT_EXPORT.json" in names

    # generated_tests and .meta excluded (required #5, #6)
    assert not any(n.startswith("generated_tests") for n in names)
    assert not any(part == ".meta" for n in names for part in n.split("/"))


def test_manifest_contents_correct(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "manifest_proj", repair_state="applied")
    res = _export(client, pid)
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    import json
    manifest = json.loads(zf.read("PROJECT_EXPORT.json").decode("utf-8"))
    assert manifest["project_id"] == pid                 # required #7
    assert manifest["origin"] == "upload"
    assert manifest["pipeline_overall_status"] == "completed"
    assert manifest["repair_application_state"] == "applied"
    assert set(manifest.keys()) == {
        "project_id", "origin", "exported_at_utc",
        "pipeline_overall_status", "repair_application_state",
    }


def test_manifest_defaults_to_not_applied_without_repair(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "no_repair_proj")  # no repair.json
    res = _export(client, pid)
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    import json
    manifest = json.loads(zf.read("PROJECT_EXPORT.json").decode("utf-8"))
    assert manifest["repair_application_state"] == "not_applied"


@pytest.mark.parametrize(
    "status",
    [
        "running",
        "waiting_for_user",
        "waiting_for_approval",
        "failed",
        "blocked",
        "unavailable",
        "rejected",
    ],
)
def test_non_completed_states_return_409(client, tmp_path, status):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, f"st_{status}", status=status)
    res = _export(client, pid)
    assert res.status_code == 409
    assert "completed" in res.json()["detail"]
    assert f"'{status}'" in res.json()["detail"]


def test_not_started_project_returns_409(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "never_started", status=None)
    res = _export(client, pid)
    assert res.status_code == 409
    assert "pipeline" in res.json()["detail"].lower()


def test_unknown_project_returns_404(client):
    res = _export(client, "not-a-real-project")
    assert res.status_code == 404


def test_traversal_project_id_rejected(client):
    res = _export(client, "../does-not-exist")
    assert res.status_code == 404


def test_path_origin_returns_400(client, tmp_path):
    ws = tmp_path / "workspace"
    external = tmp_path / "external_proj"
    external.mkdir()
    (external / "app.py").write_text("def add(a, b):\n    return a + b\n")
    pid = _write_project(
        ws, "path_proj", origin="path",
        status="completed", source_path=str(external),
    )
    res = _export(client, pid)
    assert res.status_code == 400
    # source_path must never leak in the response
    assert str(external) not in res.text
    assert "upload-origin" in res.json()["detail"]


def test_symlink_outside_source_is_not_exported(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "symlink_proj", files={"calc.py": "x = 1\n"})
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("TOP-SECRET", encoding="utf-8")
    link = ws / pid / "source" / "leak.py"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    res = _export(client, pid)
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = zf.namelist()
    assert "leak.py" not in names
    assert not any("outside_secret" in n for n in names)
    assert "TOP-SECRET" not in res.content.decode("latin-1")


def test_ignored_directories_excluded(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "ignored_proj", files={
        "app.py": "x = 1\n",
        "node_modules/dep.js": "// should be excluded\n",
        "__pycache__/app.cpython-311.pyc": b"\x00\x01".decode("latin-1"),
        ".git/config": "[core]\n",
    })
    res = _export(client, pid)
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = zf.namelist()
    assert "app.py" in names
    assert not any(n.startswith("node_modules") for n in names)
    assert not any(n.startswith("__pycache__") for n in names)
    assert not any(n.startswith(".git") for n in names)


def test_missing_source_handled_safely(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "no_source", files={})
    import shutil
    shutil.rmtree(ws / pid / "source")
    res = _export(client, pid)
    assert res.status_code == 404
    assert "source" in res.json()["detail"].lower()


def test_export_does_not_mutate_source_or_pipeline_state(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(
        ws, "immutable_proj",
        files={"calc.py": "def add(a, b):\n    return a + b\n"},
        repair_state="applied",
    )
    source_file = ws / pid / "source" / "calc.py"
    pipeline_file = ws / pid / ".meta" / "pipeline.json"
    repair_file = ws / pid / ".meta" / "repair.json"
    before_src = source_file.read_bytes()
    before_pipe = pipeline_file.read_bytes()
    before_repair = repair_file.read_bytes()
    before_tree = sorted(
        str(p.relative_to(ws))
        for p in (ws / pid).rglob("*") if p.is_file()
    )

    res = _export(client, pid)
    assert res.status_code == 200
    assert source_file.read_bytes() == before_src
    assert pipeline_file.read_bytes() == before_pipe
    assert repair_file.read_bytes() == before_repair
    after_tree = sorted(
        str(p.relative_to(ws))
        for p in (ws / pid).rglob("*") if p.is_file()
    )
    assert after_tree == before_tree


def test_temp_zip_cleaned_up_after_response(client, tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "cleanup_proj")
    res = _export(client, pid)
    assert res.status_code == 200
    # The temp dir holding the zip is removed after the FileResponse streams.
    import tempfile as _tf
    assert list(Path(_tf.gettempdir()).glob("export_*")) == []


def test_cleanup_removes_zip_and_temp_dir(tmp_path):
    ws = tmp_path / "workspace"
    pid = _write_project(ws, "service_cleanup")
    zip_path, _ = project_export.build_project_zip(pid, workspace=ws)
    assert zip_path.is_file()
    project_export.cleanup_export_zip(zip_path)
    assert not zip_path.parent.exists()


def test_source_symlink_outside_workspace_is_refused(client, tmp_path):
    ws = tmp_path / "workspace"
    outside = tmp_path / "external_source"
    outside.mkdir()
    (outside / "app.py").write_text("print('hi')\n")
    pid = _write_project(ws, "symlink_source", files={})
    import shutil
    shutil.rmtree(ws / pid / "source")
    try:
        os.symlink(outside, ws / pid / "source")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    res = _export(client, pid)
    assert res.status_code == 400
    assert str(outside) not in res.text