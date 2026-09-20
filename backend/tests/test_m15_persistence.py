"""M15-A tests: atomic persistence (P3), corrupt-artifact handling (P4),
stuck-pipeline recovery (P1+O4), and upload auto-start failure visibility (P6).

Uses the existing deterministic stub pattern: milestone stage services are
stubbed at the orchestrator boundary (pipeline._EXEC) so state-machine,
recovery, and persistence behavior is tested without Docker.
"""

from datetime import datetime, timedelta, timezone

import json

from app.core import config
from app.models.execution import (
    STATUS_PASSED,
    ExecutionSummary,
    TestExecutionResult,
)
from app.models.pipeline import (
    PIPELINE_RUNNING,
    PIPELINE_UNAVAILABLE,
    PIPELINE_WAITING_USER,
    PipelineState,
    StageRecord,
    STAGE_SUCCESS,
)
from app.services import pipeline as pl
from app.services import project_ingestion as ingestion
from app.execution import runner


def _now():
    return datetime.now(timezone.utc)


def _old():
    return _now() - timedelta(seconds=2 * config.PIPELINE_STUCK_TIMEOUT_SECONDS)


def _mk_project(ws, files=None):
    files = files or [("app.py", b"def add(a, b):\n    return a + b\n")]
    return ingestion.save_upload(files, ws).project_id


def _fake_executor(ws, pid, stage, status, artifact=None):
    if artifact is not None:
        name, payload = artifact
        p = ws / pid / ".meta" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
    if stage == "execute" and status == pl.STAGE_SUCCESS:
        return (status, "id", "execute: success", [])
    return (status, f"id-{stage}", f"{stage}: {status}", [])


def _patch(monkeypatch, stage, status=pl.STAGE_SUCCESS, artifact=None):
    monkeypatch.setitem(
        pl._EXEC, stage,
        lambda ws, pid, _s=stage, _st=status, _a=artifact: _fake_executor(
            ws, pid, _s, _st, _a
        ),
    )


def _running_state(ws, pid, started, updated):
    """Persist a hand-built `running` state with explicit timestamps."""
    state = PipelineState(
        project_id=pid, pipeline_id="pipe", current_stage="profiling",
        overall_status=PIPELINE_RUNNING, stage_started_at=started, updated_at=updated,
    )
    state.stage_history.append(StageRecord(
        stage="upload", status=STAGE_SUCCESS,
        start_time=_now(), end_time=_now(), reason="Upload succeeded.",
    ))
    state.completed_stages.append("upload")
    ingestion.save_pipeline(ws, state.model_dump_json())
    return state


def _execution_json(ws, pid):
    result = TestExecutionResult(
        project_id=pid,
        overall_status=STATUS_PASSED,
        summary=ExecutionSummary(
            total_files=1, total_test_functions=2, passed=2,
            failed=0, errors=0, skipped=0,
        ),
    )
    return result.model_dump_json()


# ---------------------------------------------------------------------------
# P3 — atomic JSON persistence
# ---------------------------------------------------------------------------

def test_save_writes_authoritative_json_without_tmp_leftover(_workspace):
    pid = _mk_project(_workspace)
    pl.start_pipeline(pid, _workspace)
    meta_dir = _workspace / pid / ".meta"
    leftovers = list(meta_dir.glob("*.tmp"))
    assert leftovers == []
    assert json.loads((meta_dir / "pipeline.json").read_text(encoding="utf-8"))["project_id"] == pid


def test_atomic_write_failure_preserves_previous_content(monkeypatch, _workspace):
    pid = _mk_project(_workspace)
    ingestion.save_profile(_workspace, json.dumps({"project_id": pid, "v": 1}))
    before = (_workspace / pid / ".meta" / "profile.json").read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated crash before replace")

    monkeypatch.setattr("app.services.project_ingestion.os.replace", boom)
    with __import__("pytest").raises(OSError):
        ingestion.save_profile(_workspace, json.dumps({"project_id": pid, "v": 2}))
    after = (_workspace / pid / ".meta" / "profile.json").read_text(encoding="utf-8")
    # A failed replace never corrupts the authoritative destination.
    assert after == before
    assert json.loads(after)["v"] == 1


def _corrupt(ws, pid, name):
    p = ws / pid / ".meta" / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# P4 — corrupt artifacts (never convert corruption into success)
# ---------------------------------------------------------------------------

def test_corrupt_pipeline_state_returns_409(client, monkeypatch):
    pid = _mk_project(config.WORKSPACE_DIR)
    st = PipelineState(project_id=pid, pipeline_id="pipe")
    ingestion.save_pipeline(config.WORKSPACE_DIR, st.model_dump_json())
    _corrupt(config.WORKSPACE_DIR, pid, "pipeline")
    res = client.get(f"/api/projects/{pid}/pipeline")
    assert res.status_code == 409
    assert "corrupt" in res.json()["detail"].lower()
    res2 = client.post(f"/api/projects/{pid}/pipeline/resume")
    assert res2.status_code == 409


def test_corrupt_meta_returns_409(client, monkeypatch):
    pid = _mk_project(config.WORKSPACE_DIR)
    _corrupt(config.WORKSPACE_DIR, pid, "meta")
    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 409
    assert "corrupt" in res.json()["detail"].lower()


def test_corrupt_execution_digest_unavailable_never_passed(_workspace):
    pid = _mk_project(_workspace)
    p = _workspace / pid / ".meta" / "execution.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{corrupt", encoding="utf-8")
    from app.services.results import build_results_digest
    digest = build_results_digest(pid, _workspace)
    assert digest.overall_verdict == "unavailable"
    assert digest.execution_status is None
    assert "execution" in digest.corrupt_artifacts
    assert any("corrupt" in w.lower() for w in digest.warnings)


def test_corrupt_pipeline_recorded_but_execution_verdict_intact(_workspace):
    pid = _mk_project(_workspace)
    p = _workspace / pid / ".meta"
    p.mkdir(parents=True, exist_ok=True)
    (p / "pipeline.json").write_text("{corrupt", encoding="utf-8")
    (p / "execution.json").write_text(_execution_json(_workspace, pid), encoding="utf-8")
    from app.services.results import build_results_digest
    digest = build_results_digest(pid, _workspace)
    assert "pipeline" in digest.corrupt_artifacts
    assert "execution" not in digest.corrupt_artifacts
    assert digest.pipeline_status is None
    assert digest.overall_verdict == "passed"


def test_corrupt_artifacts_get_project_tolerant(client, monkeypatch):
    pid = _mk_project(config.WORKSPACE_DIR)
    _corrupt(config.WORKSPACE_DIR, pid, "codemap")
    _corrupt(config.WORKSPACE_DIR, pid, "retest")
    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    body = res.json()
    assert body["codemap"] is None
    assert body["retest"] is None
    assert body["repair"] is None
    assert sorted(body["corrupt_artifacts"]) == sorted(["codemap", "retest"])


def test_corrupt_repair_never_completes_approve_gate(_workspace):
    pid = _mk_project(_workspace)
    state = PipelineState(
        project_id=pid, pipeline_id="pipe", current_stage="awaiting_repair_approval",
        overall_status="waiting_for_approval",
    )
    state.stage_history.append(StageRecord(
        stage="approve", status=pl.STAGE_APPROVED, start_time=_now(), end_time=_now(),
    ))
    state.completed_stages.append("approve")
    repair_p = _workspace / pid / ".meta" / "repair.json"
    repair_p.parent.mkdir(parents=True, exist_ok=True)
    repair_p.write_text("{corrupt", encoding="utf-8")
    nxt = pl._next_action(state, _workspace)
    assert nxt[0] == "stop"
    assert nxt[1] == pl.PIPELINE_UNAVAILABLE
    assert "corrupt" in nxt[2].lower()


# ---------------------------------------------------------------------------
# P1 + O4 — stuck pipeline detection and deterministic recovery
# ---------------------------------------------------------------------------

def test_healthy_running_not_stuck(_workspace):
    pid = _mk_project(_workspace)
    _running_state(_workspace, pid, _now(), _now())
    state = pl._load(_workspace, pid)
    assert pl._stale(state, _now()) is False


def test_long_running_with_heartbeat_not_stuck(_workspace):
    pid = _mk_project(_workspace)
    _running_state(_workspace, pid, _old(), _now())
    state = pl._load(_workspace, pid)
    assert pl._stale(state, _now()) is False


def test_stale_running_recovered_to_unavailable(_workspace):
    pid = _mk_project(_workspace)
    _running_state(_workspace, pid, _old(), _old())
    state = pl.get_pipeline(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_UNAVAILABLE
    assert "abandoned" in state.reason
    assert state.stage_started_at is None


def test_recovery_idempotent(_workspace):
    pid = _mk_project(_workspace)
    _running_state(_workspace, pid, _old(), _old())
    s1 = pl.get_pipeline(pid, _workspace)
    assert s1.overall_status == pl.PIPELINE_UNAVAILABLE
    s2 = pl.get_pipeline(pid, _workspace)
    assert s2.overall_status == pl.PIPELINE_UNAVAILABLE
    assert s2.reason == s1.reason
    assert len(s2.stage_history) == len(s1.stage_history)


def test_restart_with_running_state_recovers(_workspace):
    pid = _mk_project(_workspace)
    _running_state(_workspace, pid, _old(), _old())
    state = pl.start_pipeline(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_UNAVAILABLE


def test_waiting_gate_never_recovered(_workspace):
    pid = _mk_project(_workspace)
    state = PipelineState(
        project_id=pid, pipeline_id="pipe", current_stage="awaiting_retest_decision",
        overall_status=PIPELINE_WAITING_USER, updated_at=datetime.now(timezone.utc),
    )
    state.updated_at = _old()
    assert pl._recover_if_stuck(state, _workspace) is False
    assert state.overall_status == PIPELINE_WAITING_USER


def test_resume_recovery_reruns_interrupted_stage(monkeypatch, _workspace):
    pid = _mk_project(_workspace)
    _running_state(_workspace, pid, _old(), _old())
    _patch(monkeypatch, "profile")
    state = pl.resume_pipeline(pid, _workspace)
    profile_records = [h for h in state.stage_history if h.stage == "profile"]
    assert len(profile_records) == 1
    assert profile_records[0].status == STAGE_SUCCESS


def test_recovery_resume_does_not_loop_forever(monkeypatch, _workspace):
    pid = _mk_project(_workspace)
    _running_state(_workspace, pid, _old(), _old())
    from app.models.diagnosis import DIAGNOSIS_FAILURES_DIAGNOSED, DiagnosisResult
    diag = DiagnosisResult(
        project_id=pid, created_at=_now(), overall_status=DIAGNOSIS_FAILURES_DIAGNOSED
    ).model_dump_json()
    for stage in ("profile", "discover", "plan", "generate", "execute"):
        _patch(monkeypatch, stage)
    _patch(monkeypatch, "diagnose", artifact=("diagnosis", diag))
    _patch(monkeypatch, "improve", pl.STAGE_EXHAUSTED)
    state = pl.resume_pipeline(pid, _workspace)
    # Deterministic finite advance: stops at the re-test gate, never an
    # infinite automatic retry loop.
    assert state.current_stage == "awaiting_retest_decision"
    assert state.overall_status == pl.PIPELINE_WAITING_USER


def test_prune_stale_container_on_name_conflict(monkeypatch):
    """A stale container blocking the named run is pruned, then the run
    retried once (bounded) so recovery is never permanently blocked."""
    import subprocess
    from pathlib import Path
    calls = []
    outcomes = [
        subprocess.CompletedProcess(args=[], returncode=125, stdout=b"", stderr=b"docker: Error response from daemon: ... name already in use"),
        None,  # prune call — never inspected
        subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b""),
    ]

    def fake_run(argv, **kwargs):
        calls.append(argv)
        out = outcomes.pop(0)
        if out is None:
            return subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        return out

    monkeypatch.setattr("app.execution.runner.subprocess.run", fake_run)

    result = runner._docker_run(
        "exec_x", str(Path(".").resolve()), None, None, ["-v"],
        120, "512m", 1.0, "img",
    )
    assert result[0] == 0 and result[4] is False
    prune = [a for a in calls if a[:3] == ["docker", "rm", "-f"]]
    assert len(prune) == 1
    assert prune[0][3] == "exec_x"
    runs = [a for a in calls if a[:2] == ["docker", "run"]]
    assert len(runs) == 2


# ---------------------------------------------------------------------------
# P6 — upload auto-start failure visibility
# ---------------------------------------------------------------------------

def test_upload_auto_start_failure_visible_and_recoverable(client, monkeypatch, caplog):
    import logging
    def boom(*a, **k):
        raise RuntimeError("simulated auto-start crash")
    monkeypatch.setattr(pl, "start_pipeline", boom)

    with caplog.at_level(logging.ERROR):
        res = client.post(
            "/api/projects/upload",
            files=[("files", ("calc.py", b"def add(a, b):\n    return a + b\n"))],
        )
    # Upload still succeeds — the pipeline is best-effort.
    assert res.status_code == 200
    pid = res.json()["project_id"]

    # Failure is logged, never silently discarded.
    assert any("auto-start failed" in r.message for r in caplog.records)

    # Failure is visible through authoritative pipeline state with a safe
    # reason and Resume as the recoverable action.
    pipe = client.get(f"/api/projects/{pid}/pipeline")
    assert pipe.status_code == 200
    body = pipe.json()
    assert body["overall_status"] == "unavailable"
    assert "Resume" in body["reason"]
    assert body["user_decision_required"] is False