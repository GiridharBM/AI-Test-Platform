"""L1 backend project index tests (GET /api/projects).

Projects are seeded through the ingestion service (no pipeline/docker), so
the tests exercise the read-only listing contract in isolation.
"""

import logging

from app.core import config
from app.services import project_ingestion as ingestion


def _seed_uploads(n=1):
    ids = []
    for i in range(n):
        meta = ingestion.save_upload([(f"f{i}.py", b"def f():\n    pass\n")])
        ids.append(meta.project_id)
    return ids


def _seed_path_project(tmp_path, name="proj"):
    d = tmp_path / name
    d.mkdir()
    (d / "app.py").write_text("def f():\n    pass\n", encoding="utf-8")
    meta = ingestion.register_local_project(str(d))
    return meta


def test_index_empty_workspace(client, _workspace):
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert res.json() == []


def test_index_ignores_directories_without_meta(client, _workspace):
    (config.WORKSPACE_DIR / "junk").mkdir()
    (config.WORKSPACE_DIR / "junk" / "x.txt").write_text("x", encoding="utf-8")
    (config.WORKSPACE_DIR / "stray-file").write_text("x", encoding="utf-8")
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert res.json() == []


def test_index_returns_only_safe_summary_fields(client, _workspace, tmp_path):
    pid_upload = _seed_uploads()[0]
    path = _seed_path_project(tmp_path)

    res = client.get("/api/projects")
    assert res.status_code == 200
    body = res.json()

    by_id = {p["project_id"]: p for p in body}
    assert set(by_id) == {pid_upload, path.project_id}

    for entry in body:
        assert set(entry) == {
            "project_id", "name", "origin", "file_count", "created_at",
            "profiled",
        }
        assert "source_path" not in entry

    assert by_id[pid_upload]["origin"] == "upload"
    assert by_id[pid_upload]["file_count"] == 1
    assert by_id[path.project_id]["origin"] == "path"
    assert by_id[path.project_id]["created_at"]


def test_index_order_is_deterministic(client, _workspace):
    ids = _seed_uploads(3)
    first = client.get("/api/projects").json()
    second = client.get("/api/projects").json()
    assert [p["project_id"] for p in first] == sorted(ids)
    assert [p["project_id"] for p in second] == sorted(ids)
    assert first == second


def test_index_skips_corrupt_meta_gracefully(client, _workspace, caplog):
    pid_ok = _seed_uploads()[0]
    (config.WORKSPACE_DIR / "corrupt_proj" / ".meta").mkdir(parents=True)
    (config.WORKSPACE_DIR / "corrupt_proj" / ".meta" / "meta.json").write_text(
        "not json", encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="app.services.project_ingestion"):
        res = client.get("/api/projects")
    assert res.status_code == 200
    assert [p["project_id"] for p in res.json()] == [pid_ok]
    events = [
        r.fields.get("event") for r in caplog.records
        if getattr(r, "fields", None)
    ]
    assert "project_index_skip_corrupt" in events