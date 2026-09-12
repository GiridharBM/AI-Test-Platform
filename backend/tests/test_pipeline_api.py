"""API tests for the sequential gated pipeline endpoints."""

from datetime import datetime, timezone

from app.models.diagnosis import (
    DIAGNOSIS_FAILURES_DIAGNOSED,
    DiagnosisResult,
)
from app.models.repair import (
    FINAL_VALIDATION_PASSED,
    REPAIR_APPLIED,
    REPAIR_VALIDATED_PENDING_APPROVAL,
    FinalValidation,
    RepairResult,
)
from app.models.retest import RETEST_STILL_FAILING, ReTestResult
from app.services import pipeline as pl


def _now():
    return datetime.now(timezone.utc)


def _diag_json(overall):
    return DiagnosisResult(project_id="p", created_at=_now(), overall_status=overall).model_dump_json()


def _retest_json(status):
    return ReTestResult(project_id="p", created_at=_now(), status=status).model_dump_json()


def _repair_json(status, fv_status):
    r = RepairResult(project_id="p", created_at=_now(), status=status)
    r.final_validation = FinalValidation(status=fv_status)
    return r.model_dump_json()


def _executor(ws, pid, stage, status, artifact=None):
    if artifact is not None:
        name, payload = artifact
        p = ws / pid / ".meta" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
    return (status, f"id-{stage}", f"{stage}: {status}", [])


def _patch(monkeypatch, stage, status, artifact=None):
    monkeypatch.setitem(
        pl._EXEC, stage,
        lambda ws, pid, _s=stage, _st=status, _a=artifact: _executor(
            ws, pid, _s, _st, _a
        ),
    )


def _register_from_path(client, tmp_path, name="proj"):
    d = tmp_path / name
    d.mkdir()
    (d / "app.py").write_text("def add(a, b):\n    return a + b\n")
    res = client.post("/api/projects/from-path", json={"path": str(d)})
    assert res.status_code == 200
    return res.json()["project_id"]


def _patch_auto(monkeypatch):
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    _patch(monkeypatch, "improve", pl.STAGE_EXHAUSTED)


def test_upload_auto_starts_pipeline(client, monkeypatch):
    """Upload success auto-profiles without any manual call (acceptance #1)."""
    from app.models.execution import STATUS_UNAVAILABLE, TestExecutionResult
    monkeypatch.setattr(pl, "execute_tests",
                        lambda *a, **k: TestExecutionResult(
                            project_id="p", created_at=_now(), overall_status=STATUS_UNAVAILABLE))
    res = client.post(
        "/api/projects/upload",
        files=[("files", ("calc.py", b"def add(a, b):\n    return a + b\n"))],
    )
    assert res.status_code == 200
    pid = res.json()["project_id"]
    # upload response shape is unchanged (ProjectMeta)
    assert "current_stage" not in res.json()

    pipe = client.get(f"/api/projects/{pid}/pipeline")
    assert pipe.status_code == 200
    body = pipe.json()
    stages = [h["stage"] for h in body["stage_history"]]
    assert "upload" in stages and "profile" in stages and "discover" in stages
    # an M6 `unavailable` execution result stops the pipeline before diagnose
    assert body["overall_status"] == "unavailable"
    assert "diagnose" not in stages


def test_pipeline_get_404_when_not_started(client, tmp_path):
    pid = _register_from_path(client, tmp_path)
    res = client.get(f"/api/projects/{pid}/pipeline")
    assert res.status_code == 404


def test_start_endpoint_and_idempotency(client, tmp_path, monkeypatch):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    res1 = client.post(f"/api/projects/{pid}/pipeline/start")
    assert res1.status_code == 200
    assert res1.json()["current_stage"] == "awaiting_retest_decision"
    res2 = client.post(f"/api/projects/{pid}/pipeline/start")
    assert res2.status_code == 200
    assert res1.json()["pipeline_id"] == res2.json()["pipeline_id"]
    assert len(res1.json()["stage_history"]) == len(res2.json()["stage_history"])


def test_full_gate_flow_via_endpoints(client, tmp_path, monkeypatch):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)

    state = client.post(f"/api/projects/{pid}/pipeline/start").json()
    assert state["current_stage"] == "awaiting_retest_decision"
    assert state["available_actions"] == ["retest", "skip_retest"]
    assert state["user_decision_required"] is True

    _patch(monkeypatch, "retest", pl.STAGE_SUCCESS,
           artifact=("retest", _retest_json(RETEST_STILL_FAILING)))
    state = client.post(f"/api/projects/{pid}/pipeline/retest").json()
    assert state["current_stage"] == "awaiting_repair_decision"
    assert state["available_actions"] == ["repair", "skip_repair"]

    _patch(monkeypatch, "repair", pl.STAGE_SUCCESS,
           artifact=("repair", _repair_json(REPAIR_VALIDATED_PENDING_APPROVAL, "not_run")))
    state = client.post(f"/api/projects/{pid}/pipeline/repair").json()
    assert state["current_stage"] == "awaiting_repair_approval"
    assert state["available_actions"] == ["approve", "reject"]
    assert state["overall_status"] == "waiting_for_approval"

    _patch(monkeypatch, "approve", pl.STAGE_APPROVED,
           artifact=("repair", _repair_json(REPAIR_APPLIED, FINAL_VALIDATION_PASSED)))
    state = client.post(f"/api/projects/{pid}/pipeline/approve").json()
    assert state["overall_status"] == "completed"
    assert state["current_stage"] == "completed"


def test_gate_action_rejected_out_of_order(client, tmp_path, monkeypatch):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    client.post(f"/api/projects/{pid}/pipeline/start")
    res = client.post(f"/api/projects/{pid}/pipeline/repair")
    assert res.status_code == 409
    assert "awaiting_repair_decision" in res.json()["detail"]
    res = client.post(f"/api/projects/{pid}/pipeline/approve")
    assert res.status_code == 409


def test_skip_flow_completes(client, tmp_path, monkeypatch):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    client.post(f"/api/projects/{pid}/pipeline/start")
    state = client.post(f"/api/projects/{pid}/pipeline/skip-retest").json()
    assert state["current_stage"] == "awaiting_repair_decision"
    state = client.post(f"/api/projects/{pid}/pipeline/skip-repair").json()
    assert state["overall_status"] == "completed"


def test_reject_flow_records_rejection(client, tmp_path, monkeypatch):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    client.post(f"/api/projects/{pid}/pipeline/start")
    _patch(monkeypatch, "retest", pl.STAGE_SUCCESS,
           artifact=("retest", _retest_json(RETEST_STILL_FAILING)))
    client.post(f"/api/projects/{pid}/pipeline/retest")
    _patch(monkeypatch, "repair", pl.STAGE_SUCCESS,
           artifact=("repair", _repair_json(REPAIR_VALIDATED_PENDING_APPROVAL, "not_run")))
    client.post(f"/api/projects/{pid}/pipeline/repair")
    state = client.post(f"/api/projects/{pid}/pipeline/reject").json()
    assert state["overall_status"] == "rejected"
    assert "rejected" in state["reason"].lower()


def test_resume_endpoint_noop_at_gate(client, tmp_path, monkeypatch):
    _patch_auto(monkeypatch)
    pid = _register_from_path(client, tmp_path)
    client.post(f"/api/projects/{pid}/pipeline/start")
    state = client.post(f"/api/projects/{pid}/pipeline/resume").json()
    assert state["current_stage"] == "awaiting_retest_decision"