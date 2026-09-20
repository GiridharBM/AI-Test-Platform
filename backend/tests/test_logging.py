"""O1 structured-logging tests.

Covers the formatter/configuration unit behaviour plus representative
lifecycle events (pipeline start / stage transitions / completion / failure /
stuck recovery / corrupt detection / user actions / ingestion events) using
caplog against the real service and API paths.
"""

import json
import logging

from app.core.logging import StructuredFormatter, configure_logging
from app.services import pipeline as pl
from app.services import project_ingestion as ingestion

from test_pipeline_api import (
    _patch,
    _patch_auto,
    _register_from_path,
    _repair_json,
    _retest_json,
)


def _record(msg="hello", level=logging.INFO, fields=None) -> logging.LogRecord:
    record = logging.LogRecord(
        "test.logging", level, __file__, 1, msg, None, None,
    )
    if fields is not None:
        record.fields = fields
    return record


def _events(records):
    return [r.fields.get("event") for r in records if getattr(r, "fields", None)]


# ---------------------------------------------------------------------------
# Formatter / configuration
# ---------------------------------------------------------------------------

def test_formatter_emits_structured_deterministic_json():
    line = json.loads(StructuredFormatter().format(_record(
        msg="hello", fields={"event": "test_event", "project_id": "p1"},
    )))
    assert line["level"] == "INFO"
    assert line["logger"] == "test.logging"
    assert line["msg"] == "hello"
    assert line["event"] == "test_event"
    assert line["project_id"] == "p1"
    assert list(line) == sorted(line)


def test_configure_logging_is_idempotent():
    root = logging.getLogger()
    before = sum(
        1 for h in root.handlers if getattr(h, "_atp_structured", False)
    )
    configure_logging()
    after = sum(
        1 for h in root.handlers if getattr(h, "_atp_structured", False)
    )
    assert before >= 1
    assert after == before


# ---------------------------------------------------------------------------
# Pipeline lifecycle events
# ---------------------------------------------------------------------------

def test_pipeline_start_and_stage_events(client, tmp_path, monkeypatch, caplog):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    with caplog.at_level(logging.INFO, logger="app.services.pipeline"):
        res = client.post(f"/api/projects/{pid}/pipeline/start")
    assert res.status_code == 200
    events = _events(caplog.records)
    assert "pipeline_started" in events
    assert "stage_started" in events
    assert "stage_completed" in events
    for record in caplog.records:
        fields = getattr(record, "fields", None)
        if not fields:
            continue
        if fields.get("event") == "stage_completed":
            assert fields["stage"] in pl._EXEC
            assert "status" in fields
            assert "duration_seconds" in fields
            assert "project_id" in fields


def test_pipeline_completion_logged(client, tmp_path, monkeypatch, caplog):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    with caplog.at_level(logging.INFO, logger="app.services.pipeline"):
        client.post(f"/api/projects/{pid}/pipeline/start")
        client.post(f"/api/projects/{pid}/pipeline/skip-retest")
        res = client.post(f"/api/projects/{pid}/pipeline/skip-repair")
    assert res.status_code == 200
    assert res.json()["overall_status"] == pl.PIPELINE_COMPLETED
    assert "pipeline_completed" in _events(caplog.records)


def test_pipeline_failure_logged_as_error(client, tmp_path, monkeypatch, caplog):
    _patch(monkeypatch, "profile", pl.STAGE_FAILED)
    pid = _register_from_path(client, tmp_path)
    with caplog.at_level(logging.INFO, logger="app.services.pipeline"):
        res = client.post(f"/api/projects/{pid}/pipeline/start")
    assert res.status_code == 200
    assert res.json()["overall_status"] == pl.PIPELINE_FAILED
    stopped = [
        r for r in caplog.records
        if getattr(r, "fields", {}).get("event") == "pipeline_stopped"
    ]
    assert len(stopped) == 1
    assert stopped[0].levelno == logging.ERROR
    assert stopped[0].fields["status"] == pl.PIPELINE_FAILED


def test_stuck_recovery_logged(client, tmp_path, monkeypatch, caplog):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    client.post(f"/api/projects/{pid}/pipeline/start")
    state = json.loads(ingestion.read_pipeline(pl.config.WORKSPACE_DIR, pid))
    state["overall_status"] = pl.PIPELINE_RUNNING
    state["updated_at"] = "2020-01-01T00:00:00Z"
    state["stage_started_at"] = "2020-01-01T00:00:00Z"
    ingestion.save_pipeline(pl.config.WORKSPACE_DIR, json.dumps(state))
    with caplog.at_level(logging.INFO, logger="app.services.pipeline"):
        res = client.get(f"/api/projects/{pid}/pipeline")
    assert res.status_code == 200
    assert res.json()["overall_status"] == pl.PIPELINE_UNAVAILABLE
    assert "pipeline_stuck_recovered" in _events(caplog.records)


def test_corrupt_pipeline_state_logged(client, tmp_path, monkeypatch, caplog):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    client.post(f"/api/projects/{pid}/pipeline/start")
    p = pl.config.WORKSPACE_DIR / pid / ".meta" / "pipeline.json"
    p.write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="app.services.pipeline"):
        res = client.get(f"/api/projects/{pid}/pipeline")
    assert res.status_code == 409
    assert "pipeline_corrupt_state" in _events(caplog.records)


def test_corrupt_meta_logged(client, tmp_path, caplog):
    pid = _register_from_path(client, tmp_path)
    meta_path = pl.config.WORKSPACE_DIR / pid / ".meta" / "meta.json"
    meta_path.write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="app.services.project_ingestion"):
        res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 409
    assert "project_meta_corrupt" in _events(caplog.records)


# ---------------------------------------------------------------------------
# User decision actions
# ---------------------------------------------------------------------------

def test_reject_action_logged(client, tmp_path, monkeypatch, caplog):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    client.post(f"/api/projects/{pid}/pipeline/start")
    _patch(monkeypatch, "retest", pl.STAGE_SUCCESS,
           artifact=("retest", _retest_json("still_failing")))
    client.post(f"/api/projects/{pid}/pipeline/retest")
    _patch(monkeypatch, "repair", pl.STAGE_SUCCESS,
           artifact=("repair", _repair_json("validated_pending_approval", "not_run")))
    client.post(f"/api/projects/{pid}/pipeline/repair")
    with caplog.at_level(logging.INFO, logger="app.services.pipeline"):
        res = client.post(f"/api/projects/{pid}/pipeline/reject")
    assert res.status_code == 200
    assert res.json()["overall_status"] == pl.PIPELINE_REJECTED
    assert "pipeline_action_rejected" in _events(caplog.records)


# ---------------------------------------------------------------------------
# Ingestion events
# ---------------------------------------------------------------------------

def test_upload_and_register_events_logged(client, tmp_path, monkeypatch, caplog):
    _patch_auto(monkeypatch)
    d = tmp_path / "proj"
    d.mkdir()
    (d / "app.py").write_text("def add(a, b):\n    return a + b\n")
    with caplog.at_level(logging.INFO, logger="app.services.project_ingestion"):
        up = client.post(
            "/api/projects/upload",
            files=[("files", ("calc.py", b"def calc(): pass\n"))],
        )
        reg = client.post("/api/projects/from-path", json={"path": str(d)})
    assert up.status_code == 200
    assert reg.status_code == 200
    events = _events(caplog.records)
    assert "project_uploaded" in events
    assert "project_registered" in events


def test_ingestion_logs_do_not_leak_paths(client, tmp_path, caplog):
    d = _make_external(tmp_path, "private")
    with caplog.at_level(logging.INFO, logger="app.services.project_ingestion"):
        client.post("/api/projects/from-path", json={"path": str(d)})
    leaks = [
        r for r in caplog.records
        if getattr(r, "fields", {}).get("event") == "project_registered"
        and str(d.resolve()) in repr(r.fields)
    ]
    assert leaks == []


def _make_external(tmp_path, name="proj"):
    d = tmp_path / name
    d.mkdir()
    (d / "app.py").write_text("def f():\n    pass\n")
    return d