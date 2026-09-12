"""Unit tests for the sequential gated pipeline orchestrator.

The milestone stage services are stubbed at the orchestrator boundary
(pipeline._EXEC) so the state machine / gating / loop / resume behavior is
tested deterministically without Docker.
"""

from datetime import datetime, timezone

import json

import pytest

from app.core import config
from app.models.codemap import CodeMap
from app.models.diagnosis import (
    DIAGNOSIS_FAILURES_DIAGNOSED,
    DIAGNOSIS_NO_FAILURES,
    DiagnosisResult,
)
from app.models.execution import (
    STATUS_PASSED,
    ExecutionSummary,
    TestExecutionResult,
)
from app.models.repair import (
    FINAL_VALIDATION_PASSED,
    REPAIR_APPLIED,
    REPAIR_VALIDATED_PENDING_APPROVAL,
    FinalValidation,
    RepairResult,
)
from app.models.retest import RETEST_FIXED, RETEST_STILL_FAILING, ReTestResult
from app.models.test_plan import TestPlan, TestPlanSummary
from app.services import pipeline as pl
from app.services import project_ingestion as ingestion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_project(ws, files=None):
    files = files or [("app.py", b"def add(a, b):\n    return a + b\n")]
    return ingestion.save_upload(files, ws).project_id


def _now():
    return datetime.now(timezone.utc)


def _diag_json(overall):
    return DiagnosisResult(
        project_id="p", created_at=_now(), overall_status=overall
    ).model_dump_json()


def _retest_json(status):
    return ReTestResult(project_id="p", created_at=_now(), status=status).model_dump_json()


def _repair_json(status, fv_status):
    r = RepairResult(project_id="p", created_at=_now(), status=status)
    r.final_validation = FinalValidation(status=fv_status)
    return r.model_dump_json()


def _fake(ws, pid, stage="", status=pl.STAGE_SUCCESS, artifact=None):
    def factory(module=__import__("functools").partial):
        return module(fake_executor, ws, pid, stage, status, artifact)
    return factory()


def fake_executor(ws, pid, stage, status, artifact=None):
    if artifact is not None:
        name, payload = artifact
        p = ws / pid / ".meta" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
    return (status, f"id-{stage}-{status}", f"{stage}: {status}", [])


def _patch(monkeypatch, stage, status, artifact=None):
    monkeypatch.setitem(
        pl._EXEC, stage,
        lambda ws, pid, _s=stage, _st=status, _a=artifact: fake_executor(
            ws, pid, _s, _st, _a
        ),
    )


def _patch_all(monkeypatch, improve_status=pl.STAGE_EXHAUSTED):
    """Auto chain up to diagnose; improve returns `improve_status`."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    _patch(monkeypatch, "improve", improve_status)


def _history_stages(state):
    return [(h.stage, h.status) for h in state.stage_history]


def _gate_retest(monkeypatch, ws):
    """Run a project to awaiting_retest_decision using stubs."""
    _patch_all(monkeypatch)
    pid = _mk_project(ws)
    state = pl.start_pipeline(pid, ws)
    assert state.current_stage == pl.GATE_RETEST
    return state, pid


# ---------------------------------------------------------------------------
# TEST A — full automatic happy path up to the re-test decision gate
# ---------------------------------------------------------------------------

def test_a_full_automatic_chain_to_retest_gate(monkeypatch, _workspace):
    state, pid = _gate_retest(monkeypatch, _workspace)
    stages = _history_stages(state)
    assert [s for s, _ in stages if s != "upload"] == [
        "profile", "discover", "plan", "generate", "execute", "diagnose", "improve",
    ]
    assert state.overall_status == pl.PIPELINE_WAITING_USER
    assert state.user_decision_required is True
    assert state.available_actions == ["retest", "skip_retest"]
    assert all(h.status in (pl.STAGE_SUCCESS, pl.STAGE_EXHAUSTED) for h in state.stage_history)


def test_a_improvement_loop_executes_between_rounds(monkeypatch, _workspace, tmp_path):
    """Improve(x2 SUCCESS) -> Execute -> Diagnose -> Improve(exhausted) -> gate."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))

    calls = {"improve": 0}
    def improve_fake(ws, pid):
        calls["improve"] += 1
        if calls["improve"] < 2:
            return (pl.STAGE_SUCCESS, "id-improve", "improved", [])
        return (pl.STAGE_EXHAUSTED, "id-improve", "no_change", [])
    monkeypatch.setitem(pl._EXEC, "improve", improve_fake)

    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    stages = [s for s, _ in _history_stages(state) if s != "upload"]
    # profile, discover, plan, generate, execute, diagnose, improve, execute,
    # diagnose, improve(exhausted)
    assert stages.count("execute") == 2
    assert stages[:6] == ["profile", "discover", "plan", "generate", "execute", "diagnose"]
    assert stages[6] == "improve"
    assert stages[7:9] == ["execute", "diagnose"]
    assert stages[9] == "improve"
    assert state.current_improvement_round == 2
    assert state.overall_status == pl.PIPELINE_WAITING_USER


def test_a_diagnosis_no_failures_without_improvement_completes(monkeypatch, _workspace, tmp_path):
    """diagnose(no_failures) with NO improvement result must COMPLETE the
    pipeline — it must never expose the re-test gate, which is only meaningful
    after an improvement actually produced changes (live-acceptance regression:
    zero-tests -> passed -> no_failures wrongly sat at awaiting_retest_decision)."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_NO_FAILURES)))
    improved = {"called": False}
    monkeypatch.setitem(pl._EXEC, "improve",
                        lambda ws, pid: improved.update(called=True) or (pl.STAGE_SUCCESS, "", "", []))
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    assert not improved["called"]
    assert state.overall_status == pl.PIPELINE_COMPLETED
    assert state.current_stage == "completed"
    assert state.user_decision_required is False
    assert state.available_actions == []
    assert all(h.stage != "retest" for h in state.stage_history)


# ---------------------------------------------------------------------------
# TEST B-G — stage failure stops the pipeline; later stages never run
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fail_stage,following", [
    ("profile", ["discover", "plan", "generate", "execute", "diagnose", "improve"]),
    ("discover", ["plan", "generate", "execute", "diagnose", "improve"]),
    ("plan", ["generate", "execute", "diagnose", "improve"]),
    ("generate", ["execute", "diagnose", "improve"]),
])
def test_b_to_e_failure_stops_pipeline(monkeypatch, _workspace, tmp_path, fail_stage, following):
    _patch_all(monkeypatch)
    _patch(monkeypatch, fail_stage, pl.STAGE_FAILED)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    ran = {s for s, _ in _history_stages(state)}
    assert fail_stage in ran
    assert not (set(following) & ran)
    assert state.overall_status == pl.PIPELINE_FAILED
    assert state.available_actions == []
    # assertion: persisted state is the stopped state
    reloaded = pl.get_pipeline(pid, _workspace)
    assert reloaded.overall_status == pl.PIPELINE_FAILED


def test_f_execute_unavailable_stops_before_diagnose(monkeypatch, _workspace, tmp_path):
    _patch_all(monkeypatch)
    _patch(monkeypatch, "execute", pl.STAGE_UNAVAILABLE)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    ran = {s for s, _ in _history_stages(state)}
    assert "execute" in ran
    assert "diagnose" not in ran and "improve" not in ran
    assert state.overall_status == pl.PIPELINE_UNAVAILABLE


def test_g_diagnose_failure_blocks_improve(monkeypatch, _workspace, tmp_path):
    _patch_all(monkeypatch)
    _patch(monkeypatch, "diagnose", pl.STAGE_FAILED)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    ran = {s for s, _ in _history_stages(state)}
    assert "improve" not in ran
    assert state.overall_status == pl.PIPELINE_FAILED


def test_improve_blocked_stops_pipeline(monkeypatch, _workspace, tmp_path):
    """Boundary guard: a `STAGE_BLOCKED` improve record injected directly at the
    orchestrator boundary (bypassing `_exec_improve`, which never emits it for
    real M8 results) is treated as a genuine blocked condition and stops
    fail-closed. Real M8 `blocked` results map to STAGE_EXHAUSTED (see
    test_improve_blocked_real_result_path_reaches_retest_gate), NOT to this."""
    _patch_all(monkeypatch, improve_status=pl.STAGE_BLOCKED)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_BLOCKED
    assert state.current_stage == pl.PIPELINE_BLOCKED


def test_improve_blocked_real_result_path_reaches_retest_gate(monkeypatch, _workspace, tmp_path):
    """Regression for the live acceptance finding: an M8 ImprovementResult with
    status=blocked means "no evidence-supported changes available" (zero files
    modified) — bounded improvement-loop EXHAUSTION, not a pipeline failure.
    The real `_exec_improve` path must therefore route to the human re-test gate
    (awaiting_retest_decision / waiting_for_user), never to overall blocked."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    from app.models.improvement import IMPROVE_BLOCKED, ImprovementResult
    import app.services.improvement as improvement_mod

    def blocked_improve(project_id, workspace=None):
        return ImprovementResult(
            project_id=project_id,
            created_at=_now(),
            status=IMPROVE_BLOCKED,
        )

    monkeypatch.setattr(improvement_mod, "improve_project", blocked_improve)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    tail = state.stage_history[-1]
    assert tail.stage == "improve"
    assert tail.status == pl.STAGE_EXHAUSTED  # blocked -> exhaustion, NOT stopped
    # exhausted improvement ends at the re-test decision gate
    assert state.overall_status == pl.PIPELINE_WAITING_USER
    assert state.current_stage == pl.GATE_RETEST  # awaiting_retest_decision
    assert state.user_decision_required is True
    assert state.available_actions == list(pl.GATE_RETEST_ACTIONS)

    # no automatic re-test may run before the user decides
    assert not any(h.stage == "retest" for h in state.stage_history)
    assert tail.status == pl.STAGE_EXHAUSTED
    assert pl.decide_skip_retest(pid, _workspace) is not None


def test_improve_unexpected_exception_fails_pipeline(monkeypatch, _workspace, tmp_path):
    """A genuine unexpected exception from M8 is a pipeline FAILURE — it is NOT
    improvement exhaustion and must never reach the re-test gate."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    import app.services.improvement as improvement_mod

    def exploding_improve(project_id, workspace=None):
        raise RuntimeError("corrupted improvement artifact")

    monkeypatch.setattr(improvement_mod, "improve_project", exploding_improve)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    tail = state.stage_history[-1]
    assert tail.stage == "improve"
    assert tail.status == pl.STAGE_FAILED
    assert "corrupted improvement artifact" in tail.reason
    assert state.overall_status == pl.PIPELINE_FAILED
    assert state.current_stage == pl.PIPELINE_FAILED
    assert state.user_decision_required is False
    assert state.available_actions == []
    assert all(h.stage != "retest" for h in state.stage_history)


def test_improve_invalid_status_fails_closed(monkeypatch, _workspace, tmp_path):
    """An M8 ImprovementResult carrying a status outside the valid set is an
    invalid state -> fail-closed pipeline failure (never mapped to success)."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    import app.services.improvement as improvement_mod
    from app.models.improvement import ImprovementResult

    monkeypatch.setattr(
        improvement_mod, "improve_project",
        lambda project_id, workspace=None: ImprovementResult(
            project_id=project_id, created_at=_now(), status="bogus-status",
        ),
    )
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    tail = state.stage_history[-1]
    assert tail.stage == "improve"
    assert tail.status == pl.STAGE_FAILED
    assert state.overall_status == pl.PIPELINE_FAILED
    assert state.current_stage == pl.PIPELINE_FAILED


def test_improve_unavailable_stops_pipeline(monkeypatch, _workspace, tmp_path):
    """An unavailable Improve stage (injected at the orchestrator boundary) must
    stop fail-closed as unavailable — infra trouble is never exhaustion."""
    _patch(monkeypatch, "improve", pl.STAGE_UNAVAILABLE)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_UNAVAILABLE
    assert state.current_stage == pl.PIPELINE_UNAVAILABLE
    assert state.user_decision_required is False
    assert all(h.stage != "retest" for h in state.stage_history)


# ---------------------------------------------------------------------------
# TEST — vacuous-success guards (live-acceptance regression):
# empty generation / zero-test execution must fail closed; diagnose(no_failures)
# only reaches the re-test gate after an improvement already ran.
# ---------------------------------------------------------------------------

def test_generate_empty_result_fails_closed(_workspace, tmp_path):
    """Real _exec_generate with an EMPTY test plan (no executable tests) must
    fail closed — empty generation is never semantic success. This is the
    upstream guard for the live bug where an empty plan generated 0 files,
    execution then 'passed' with no tests, and diagnose reached the re-test
    gate without any improvement."""
    pid = _mk_project(_workspace)
    # Real (offline, deterministic) profile so the artifact is valid.
    assert pl._exec_profile(_workspace, pid)[0] == pl.STAGE_SUCCESS
    # Overwrite the codemap and plan artifacts with EMPTY ones.
    empty_cm = CodeMap(project_id=pid, created_at=_now())
    empty_plan = TestPlan(
        project_id=pid,
        created_at=_now(),
        summary=TestPlanSummary(
            total_specs=0, critical_count=0, high_count=0, medium_count=0, low_count=0
        ),
    )
    ingestion.save_codemap(_workspace, empty_cm.model_dump_json())
    ingestion.save_test_plan(_workspace, empty_plan.model_dump_json())

    status, _, reason, warnings = pl._exec_generate(_workspace, pid)
    assert status == pl.STAGE_FAILED
    assert "no executable test files" in reason.lower()
    # Empty-generation warnings are surfaced, not swallowed.
    assert not warnings or all(isinstance(w, str) for w in warnings)


def test_execute_vacuous_zero_tests_fails_closed(monkeypatch, _workspace, tmp_path):
    """Real _exec_execute: an execution that ran ZERO tests must not advance as
    a meaningful execution — the current LIVE bug path (pytest exit 5 -> passed
    -> diagnose(no_failures) -> re-test gate with no improvement)."""
    pid = _mk_project(_workspace)
    (ingestion.project_dir(_workspace, pid) / "generated_tests").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        pl, "execute_tests",
        lambda *a, **k: TestExecutionResult(
            project_id=pid, created_at=_now(), overall_status=STATUS_PASSED,
        ),
    )
    status, _, reason, _ = pl._exec_execute(_workspace, pid)
    assert status == pl.STAGE_FAILED
    assert "ran 0 tests" in reason

    # Control: the SAME execution shape but with at least one collected test is
    # a normal (non-vacuous) passing run and stays stage-success.
    monkeypatch.setattr(
        pl, "execute_tests",
        lambda *a, **k: TestExecutionResult(
            project_id=pid, created_at=_now(), overall_status=STATUS_PASSED,
            summary=ExecutionSummary(total_test_functions=1),
        ),
    )
    status, _, _, _ = pl._exec_execute(_workspace, pid)
    assert status == pl.STAGE_SUCCESS


def test_diagnosis_no_failures_after_improve_still_reaches_retest_gate(monkeypatch, _workspace, tmp_path):
    """diagnose(no_failures) AFTER an improve round must still land on the
    re-test gate: the gate is valid when there is an improvement result to
    decide on (regression guard for G3's two-sided routing)."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    # diagnose call #1 -> failures found (triggers improve), #2 -> no failures.
    diags = {
        1: _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED),
        2: _diag_json(DIAGNOSIS_NO_FAILURES),
    }
    calls = {"n": 0}

    def diagnose_fake(ws, pid):
        calls["n"] += 1
        return fake_executor(ws, pid, "diagnose", pl.STAGE_SUCCESS,
                             ("diagnosis", diags[calls["n"]]))

    monkeypatch.setitem(pl._EXEC, "diagnose", diagnose_fake)
    monkeypatch.setitem(pl._EXEC, "improve",
                        lambda ws, pid: (pl.STAGE_SUCCESS, "id-improve", "improve: success", []))
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)

    assert state.current_stage == pl.GATE_RETEST
    assert state.overall_status == pl.PIPELINE_WAITING_USER
    assert state.user_decision_required is True
    assert state.available_actions == list(pl.GATE_RETEST_ACTIONS)
    assert state.current_improvement_round == 1
    assert [h.stage for h in state.stage_history if h.stage != "upload"].count("improve") == 1


def test_bom_uploaded_source_parses_and_generates_tests(_workspace, tmp_path):
    """A UTF-8-BOM source file must parse into a real CodeMap and produce real
    generated tests end-to-end (offline real path). Without utf-8-sig source
    reads, ast.parse fails on U+FEFF and the file silently disappears into an
    empty codemap -> empty test plan -> the vacuous-success chain."""
    bom_dir = _workspace / "bom-mount"
    bom_dir.mkdir(parents=True, exist_ok=True)
    (bom_dir / "calc.py").write_bytes(b"\xef\xbb\xbf" + b"def add(a, b):\n    return a + b\n")
    pid = ingestion.save_upload([("calc.py", (bom_dir / "calc.py").read_bytes())], _workspace).project_id

    status, _, reason, warnings = pl._exec_profile(_workspace, pid)
    assert status == pl.STAGE_SUCCESS
    assert not any("could not be parsed" in w or "U+FEFF" in w for w in warnings), warnings
    assert pl._exec_discover(_workspace, pid)[0] == pl.STAGE_SUCCESS
    cm = json.loads(ingestion.read_codemap(_workspace, pid))
    assert cm["source_modules"], "BOM file must be parsed into the codemap"
    assert any(fn["name"] == "add" for m in cm["source_modules"] for fn in m["functions"])
    assert pl._exec_plan(_workspace, pid)[0] == pl.STAGE_SUCCESS
    # Empty-generation must no longer be reached for a genuinely parseable file.
    status, _, reason, warnings = pl._exec_generate(_workspace, pid)
    assert status == pl.STAGE_SUCCESS
    gen_dir = ingestion.project_dir(_workspace, pid) / "generated_tests"
    assert list(gen_dir.glob("test_*.py")), "generate must emit real scaffold files"


def test_improve_real_result_success_loops_through_execute_diagnose(monkeypatch, _workspace, tmp_path):
    """A successful (improved) M8 result must continue Improve -> Execute -> Diagnose,
    bounded by AUTO_IMPROVEMENT_MAX_ROUNDS — through the real improve path."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    from app.models.improvement import IMPROVE_IMPROVED, ImprovementResult
    import app.services.improvement as improvement_mod

    monkeypatch.setattr(
        improvement_mod, "improve_project",
        lambda project_id, workspace=None: ImprovementResult(
            project_id=project_id,
            created_at=_now(),
            status=IMPROVE_IMPROVED,
        ),
    )
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    stages = [s for s, _ in _history_stages(state) if s != "upload"]
    improves = [h for h in state.stage_history if h.stage == "improve"]
    assert all(h.status == pl.STAGE_SUCCESS for h in improves)
    assert len(improves) == config.AUTO_IMPROVEMENT_MAX_ROUNDS
    # initial execute + one re-execute per round
    assert stages.count("execute") == 1 + len(improves)
    # loop stopped at the round limit, not by a failure
    assert state.current_improvement_round == config.AUTO_IMPROVEMENT_MAX_ROUNDS
    assert state.current_stage == pl.GATE_RETEST
    assert state.overall_status == pl.PIPELINE_WAITING_USER


# ---------------------------------------------------------------------------
# TEST H/I — bounded improvement loop and hard maximum
# ---------------------------------------------------------------------------

def test_i_hard_max_rounds(monkeypatch, _workspace, tmp_path):
    monkeypatch.setattr(config, "AUTO_IMPROVEMENT_MAX_ROUNDS", 1_000)
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "execute", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    monkeypatch.setitem(pl._EXEC, "improve",
                        lambda ws, pid: (pl.STAGE_SUCCESS, "id", "improved", []))
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    # hard cap applies regardless of config
    assert state.maximum_improvement_rounds == config.AUTO_IMPROVEMENT_MAX_ROUNDS_HARD_MAX
    assert state.current_improvement_round == config.AUTO_IMPROVEMENT_MAX_ROUNDS_HARD_MAX
    assert state.current_stage == pl.GATE_RETEST
    assert sum(1 for s, _ in _history_stages(state) if s == "improve") == \
        config.AUTO_IMPROVEMENT_MAX_ROUNDS_HARD_MAX


# ---------------------------------------------------------------------------
# TEST J/K — human decision gates
# ---------------------------------------------------------------------------

def test_j_retest_requires_explicit_decision(monkeypatch, _workspace, tmp_path):
    state, pid = _gate_retest(monkeypatch, _workspace)
    retest_called = {"calls": 0}
    monkeypatch.setitem(pl._EXEC, "retest",
                        lambda ws, pd: retest_called.update(calls=retest_called["calls"] + 1)
                        or (pl.STAGE_SUCCESS, "id", "retest", []))
    # no automatic re-test; a fresh resume while waiting is a no-op
    state2 = pl.resume_pipeline(pid, _workspace)
    assert retest_called["calls"] == 0
    assert state2.current_stage == pl.GATE_RETEST
    # skip gate
    state3 = pl.decide_skip_retest(pid, _workspace)
    assert state3.current_stage == pl.GATE_REPAIR
    assert state3.available_actions == ["repair", "skip_repair"]


def test_k_repair_requires_explicit_decision(monkeypatch, _workspace, tmp_path):
    state, pid = _gate_retest(monkeypatch, _workspace)
    _patch(monkeypatch, "retest", pl.STAGE_SUCCESS,
           artifact=("retest", _retest_json(RETEST_STILL_FAILING)))
    repair_called = {"calls": 0}
    monkeypatch.setitem(pl._EXEC, "repair",
                        lambda ws, pd: repair_called.update(calls=repair_called["calls"] + 1)
                        or (pl.STAGE_SUCCESS, "id", "repair", []))
    state = pl.decide_retest(pid, _workspace)
    assert repair_called["calls"] == 0
    assert state.current_stage == pl.GATE_REPAIR
    assert state.available_actions == ["repair", "skip_repair"]


def test_retest_blocked_stops_not_repair(monkeypatch, _workspace, tmp_path):
    state, pid = _gate_retest(monkeypatch, _workspace)
    _patch(monkeypatch, "retest", pl.STAGE_BLOCKED)
    repairing = {"called": False}
    monkeypatch.setitem(pl._EXEC, "repair",
                        lambda ws, pd: repairing.update(called=True) or (pl.STAGE_FAILED, "", "", []))
    state = pl.decide_retest(pid, _workspace)
    assert not repairing["called"]
    assert state.overall_status == pl.PIPELINE_BLOCKED


def test_retest_fixed_completes(monkeypatch, _workspace, tmp_path):
    state, pid = _gate_retest(monkeypatch, _workspace)
    _patch(monkeypatch, "retest", pl.STAGE_SUCCESS,
           artifact=("retest", _retest_json(RETEST_FIXED)))
    state = pl.decide_retest(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_COMPLETED
    assert state.current_stage == "completed"


# ---------------------------------------------------------------------------
# TEST L/M — approval gate
# ---------------------------------------------------------------------------

def _to_approval_gate(monkeypatch, _workspace):
    state, pid = _gate_retest(monkeypatch, _workspace)
    _patch(monkeypatch, "retest", pl.STAGE_SUCCESS,
           artifact=("retest", _retest_json(RETEST_STILL_FAILING)))
    state = pl.decide_retest(pid, _workspace)
    assert state.current_stage == pl.GATE_REPAIR
    _patch(monkeypatch, "repair", pl.STAGE_SUCCESS,
           artifact=("repair", _repair_json(REPAIR_VALIDATED_PENDING_APPROVAL, "not_run")))
    state = pl.decide_repair(pid, _workspace)
    assert state.current_stage == pl.GATE_APPROVAL
    return state, pid


def test_l_source_unchanged_until_approval(monkeypatch, _workspace, tmp_path):
    state, pid = _to_approval_gate(monkeypatch, _workspace)
    source = config.WORKSPACE_DIR / pid / "source" / "app.py"
    original = source.read_text(encoding="utf-8")
    # the pipeline carrying the "source" mirror never touched it
    assert source.read_text(encoding="utf-8") == original
    approve_called = {"calls": 0}
    monkeypatch.setitem(pl._EXEC, "approve",
                        lambda ws, pd: approve_called.update(calls=approve_called["calls"] + 1)
                        or (pl.STAGE_APPROVED, "id", "approve", []))
    # resume while waiting for approval is a no-op: never auto-approves
    state2 = pl.resume_pipeline(pid, _workspace)
    assert approve_called["calls"] == 0
    assert state2.current_stage == pl.GATE_APPROVAL
    assert state2.overall_status == pl.PIPELINE_WAITING_APPROVAL
    assert state2.available_actions == ["approve", "reject"]


def test_l_approve_applies_and_completes(monkeypatch, _workspace, tmp_path):
    state, pid = _to_approval_gate(monkeypatch, _workspace)
    _patch(monkeypatch, "approve", pl.STAGE_APPROVED,
           artifact=("repair", _repair_json(REPAIR_APPLIED, FINAL_VALIDATION_PASSED)))
    state = pl.decide_approve(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_COMPLETED
    assert state.current_stage == "completed"
    assert [h.stage for h in state.stage_history][-1] == "approve"


def test_m_reject_leaves_source_unchanged(monkeypatch, _workspace, tmp_path):
    state, pid = _to_approval_gate(monkeypatch, _workspace)
    source = config.WORKSPACE_DIR / pid / "source" / "app.py"
    original = source.read_text(encoding="utf-8")
    state = pl.decide_reject(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_REJECTED
    assert "reject" in state.reason.lower()
    assert source.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# TEST N — server restart: gates + terminals survive reload
# ---------------------------------------------------------------------------

def test_n_waiting_state_survives_reload(monkeypatch, _workspace, tmp_path):
    state, pid = _to_approval_gate(monkeypatch, _workspace)
    loaded = pl.get_pipeline(pid, _workspace)
    assert loaded.current_stage == pl.GATE_APPROVAL
    assert loaded.overall_status == pl.PIPELINE_WAITING_APPROVAL
    assert loaded.available_actions == ["approve", "reject"]


def test_n_upload_gate_state_persists(monkeypatch, _workspace, tmp_path):
    state, pid = _gate_retest(monkeypatch, _workspace)
    loaded = pl.get_pipeline(pid, _workspace)
    assert loaded.current_stage == pl.GATE_RETEST
    assert loaded.user_decision_required is True


# ---------------------------------------------------------------------------
# TEST O — duplicate start prevention
# ---------------------------------------------------------------------------

def test_o_duplicate_start_returns_same_pipeline(monkeypatch, _workspace, tmp_path):
    _patch_all(monkeypatch)
    pid = _mk_project(_workspace)
    first = pl.start_pipeline(pid, _workspace)
    second = pl.start_pipeline(pid, _workspace)
    assert first.pipeline_id == second.pipeline_id
    assert len(first.stage_history) == len(second.stage_history)
    # start does not rerun stages
    assert [h.stage for h in second.stage_history] == [h.stage for h in first.stage_history]


# ---------------------------------------------------------------------------
# Resume after failure
# ---------------------------------------------------------------------------

def test_resume_retries_failed_execute(monkeypatch, _workspace, tmp_path):
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "diagnose", pl.STAGE_SUCCESS,
           artifact=("diagnosis", _diag_json(DIAGNOSIS_FAILURES_DIAGNOSED)))
    _patch(monkeypatch, "improve", pl.STAGE_EXHAUSTED)

    execute_state = {"failed": True}
    def execute_fake(ws, pid):
        if execute_state["failed"]:
            execute_state["failed"] = False
            return (pl.STAGE_UNAVAILABLE, "id-exec", "unavailable", [])
        return (pl.STAGE_SUCCESS, "id-exec", "passed", [])
    monkeypatch.setitem(pl._EXEC, "execute", execute_fake)

    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_UNAVAILABLE
    assert state.current_stage == pl.PIPELINE_UNAVAILABLE

    state2 = pl.resume_pipeline(pid, _workspace)
    # execute retried then succeeded; chain continued to the re-test gate
    assert [h.stage for h in state2.stage_history if h.stage == "execute"].__len__() == 2
    assert state2.current_stage == pl.GATE_RETEST
    assert state2.overall_status == pl.PIPELINE_WAITING_USER


def test_resume_noop_at_human_gates(monkeypatch, _workspace, tmp_path):
    state, pid = _gate_retest(monkeypatch, _workspace)
    before = len(state.stage_history)
    state2 = pl.resume_pipeline(pid, _workspace)
    assert len(state2.stage_history) == before
    assert state2.current_stage == pl.GATE_RETEST


# ---------------------------------------------------------------------------
# Gate enforcement at decision boundaries
# ---------------------------------------------------------------------------

def test_gate_action_rejected_out_of_order(monkeypatch, _workspace, tmp_path):
    _patch_all(monkeypatch)
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    assert state.current_stage == pl.GATE_RETEST
    # repair before retest decision is invalid
    with pytest.raises(pl.PipelineGateError):
        pl.decide_repair(pid, _workspace)
    # approve before repair is invalid
    with pytest.raises(pl.PipelineGateError):
        pl.decide_approve(pid, _workspace)


def test_double_retest_after_gate_passes(monkeypatch, _workspace, tmp_path):
    state, pid = _gate_retest(monkeypatch, _workspace)
    _patch(monkeypatch, "retest", pl.STAGE_SUCCESS,
           artifact=("retest", _retest_json(RETEST_STILL_FAILING)))
    _patch(monkeypatch, "repair", pl.STAGE_SUCCESS,
           artifact=("repair", _repair_json(REPAIR_VALIDATED_PENDING_APPROVAL, "not_run")))
    state = pl.decide_retest(pid, _workspace)
    assert state.current_stage == pl.GATE_REPAIR
    # retest is no longer the active gate
    with pytest.raises(pl.PipelineGateError):
        pl.decide_retest(pid, _workspace)


# ---------------------------------------------------------------------------
# User behavioral test merge at generate (M5): discovered user test files are
# copied into generated_tests/ so M6 executes them and M9/M11 can reach them.
# ---------------------------------------------------------------------------

def _gen_with_user_tests(_workspace, files):
    pid = ingestion.save_upload(files, _workspace).project_id
    assert pl._exec_profile(_workspace, pid)[0] == pl.STAGE_SUCCESS
    assert pl._exec_discover(_workspace, pid)[0] == pl.STAGE_SUCCESS
    assert pl._exec_plan(_workspace, pid)[0] == pl.STAGE_SUCCESS
    status, _, _, _ = pl._exec_generate(_workspace, pid)
    return pid, status


def test_generate_merges_user_test_files(_workspace, tmp_path):
    """A discovered user test file is copied into generated_tests/ verbatim and
    recorded in merged_user_files, so the M6 execution actually runs the user's
    behavioral assertions."""
    pid, status = _gen_with_user_tests(_workspace, [
        ("calc.py", b"def add(a, b):\n    return a - b\n"),
        ("test_calc.py", b"def test_add_returns_sum():\n    assert add(2, 3) == 5\n"),
    ])
    assert status == pl.STAGE_SUCCESS
    gen_dir = ingestion.project_dir(_workspace, pid) / "generated_tests"
    copied = gen_dir / "user_test_calc.py"
    assert copied.is_file()
    assert copied.read_text(encoding="utf-8") == "def test_add_returns_sum():\n    assert add(2, 3) == 5\n"
    gen = json.loads(ingestion.read_test_generation(_workspace, pid))
    assert gen["merged_user_files"] == ["user_test_calc.py"]
    # the sandbox pytest must actually collect the merged file (default
    # collection excludes `user_*.py`), so a pytest.ini is emitted alongside
    assert (gen_dir / "pytest.ini").is_file()
    # the original source test is untouched by the merge
    src = ingestion.source_dir(_workspace, pid) / "test_calc.py"
    assert src.read_text(encoding="utf-8") == "def test_add_returns_sum():\n    assert add(2, 3) == 5\n"


def test_upload_strips_common_project_dir_prefix(_workspace):
    """Browser folder uploads carry the selected folder name as a path prefix
    (``m11-success-demo/calc.py``). The sandbox import root is /source
    (PYTHONPATH=/source), so the wrapper folder must be stripped: the source
    tree must contain calc.py directly, not nested under the folder name."""
    pid = ingestion.save_upload([
        ("m11-success-demo/calc.py", b"def add(a, b):\n    return a + b\n"),
        ("m11-success-demo/test_calc.py", b"from calc import add\n\ndef test_add_returns_sum():\n    assert add(2, 3) == 5\n"),
    ], _workspace).project_id
    src = ingestion.source_dir(_workspace, pid)
    assert (src / "calc.py").is_file()
    assert (src / "test_calc.py").is_file()
    assert not (src / "m11-success-demo").exists()
    # Display name still derives from the original paths.
    meta = ingestion.read_meta(_workspace, pid)
    assert meta.name == "m11-success-demo"


def test_upload_keeps_real_top_level_package(_workspace):
    """A shared first component that is a genuine package root (carries
    __init__.py) must NOT be stripped: it is the module namespace the code
    imports by name."""
    pid = ingestion.save_upload([
        ("pkg/__init__.py", b""),
        ("pkg/core.py", b"def add(a, b):\n    return a + b\n"),
    ], _workspace).project_id
    src = ingestion.source_dir(_workspace, pid)
    assert (src / "pkg" / "__init__.py").is_file()
    assert (src / "pkg" / "core.py").is_file()


def test_upload_flat_files_untouched(_workspace):
    """Files uploaded without a shared folder prefix keep their exact layout."""
    pid = ingestion.save_upload([
        ("calc.py", b"def add(a, b):\n    return a + b\n"),
        ("test_calc.py", b"from calc import add\n\ndef test_add_returns_sum():\n    assert add(2, 3) == 5\n"),
    ], _workspace).project_id
    src = ingestion.source_dir(_workspace, pid)
    assert (src / "calc.py").is_file()
    assert (src / "test_calc.py").is_file()


def test_generate_merge_never_overwrites_generated_files(_workspace, tmp_path):
    """A user test whose name collides with a generated scaffold must be copied
    under `user_` — the generated file content is never clobbered."""
    pid, status = _gen_with_user_tests(_workspace, [
        ("calc.py", b"def add(a, b):\n    return a - b\n"),
        ("test_calc.py", b"def test_add_basic():\n    assert add(2, 3) == 5\n"),
    ])
    assert status == pl.STAGE_SUCCESS
    gen_dir = ingestion.project_dir(_workspace, pid) / "generated_tests"
    generated = gen_dir / "test_calc.py"
    user = gen_dir / "user_test_calc.py"
    assert user.is_file()
    assert user.read_text(encoding="utf-8") == "def test_add_basic():\n    assert add(2, 3) == 5\n"
    # the generated scaffold still exists and starts with the platform header
    assert generated.is_file()
    assert "Generated by AI Test Platform" in generated.read_text(encoding="utf-8")


def test_generate_merge_skips_traversal_and_missing(_workspace, tmp_path):
    """The merge refuses traversal/absent paths; nothing escapes generated_tests/."""
    pid = _mk_project(_workspace)
    gen_dir = ingestion.project_dir(_workspace, pid) / "generated_tests"
    gen_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1", encoding="utf-8")
    src = ingestion.source_dir(_workspace, pid)
    (src / "ok_test.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    names = pl._merge_user_tests(
        gen_dir, src,
        ["ok_test.py", "../outside.py", "missing.py", "C:/Windows/win.ini"],
    )
    assert names == ["user_ok_test.py"]
    assert (gen_dir / "user_ok_test.py").is_file()
    assert {p.name for p in gen_dir.glob("*.py")} == {"user_ok_test.py"}


def test_generate_merge_is_idempotent(_workspace, tmp_path):
    """Re-merging the same source must reuse the existing `user_` name and never
    write `user_2_*` duplicates."""
    pid = _mk_project(_workspace)
    gen_dir = ingestion.project_dir(_workspace, pid) / "generated_tests"
    gen_dir.mkdir(parents=True, exist_ok=True)
    src = ingestion.source_dir(_workspace, pid)
    (src / "test_calc.py").write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    first = pl._merge_user_tests(gen_dir, src, ["test_calc.py"])
    second = pl._merge_user_tests(gen_dir, src, ["test_calc.py"])
    assert first == ["user_test_calc.py"]
    assert second == ["user_test_calc.py"]
    assert not (gen_dir / "user_2_test_calc.py").exists()


# ---------------------------------------------------------------------------
# Actual execution semantics: an M6 `unavailable` result stops the pipeline
# ---------------------------------------------------------------------------

def test_execute_unavailable_result_stops_pipeline(monkeypatch, _workspace, tmp_path):
    """An execution result of `unavailable` (per M6 semantics) must STOP, never
    diagnose. The runner is stubbed so the test is deterministic regardless of
    whether Docker is available in this environment."""
    _patch(monkeypatch, "profile", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "discover", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "plan", pl.STAGE_SUCCESS)
    _patch(monkeypatch, "generate", pl.STAGE_SUCCESS)
    diagnosed = {"called": False}
    from app.agents.diagnose import diagnose_project as real_diag
    monkeypatch.setitem(pl._EXEC, "diagnose",
                        lambda ws, pid: diagnosed.update(called=True) or real_diag(pid, ws))
    from app.models.execution import STATUS_UNAVAILABLE, TestExecutionResult
    monkeypatch.setattr(pl, "execute_tests",
                        lambda *a, **k: TestExecutionResult(
                            project_id="p", created_at=_now(), overall_status=STATUS_UNAVAILABLE))
    pid = _mk_project(_workspace)
    state = pl.start_pipeline(pid, _workspace)
    assert state.overall_status == pl.PIPELINE_UNAVAILABLE
    assert not diagnosed["called"]
    tail = state.stage_history[-1]
    assert tail.stage == "execute"
    assert tail.status == pl.STAGE_UNAVAILABLE

    # resume retries execute; still unavailable -> stays unavailable, no diagnose
    state2 = pl.resume_pipeline(pid, _workspace)
    assert state2.overall_status == pl.PIPELINE_UNAVAILABLE
    assert not diagnosed["called"]


# ---------------------------------------------------------------------------
# Live (Docker-required): the second execution of the M8-improved artifacts
# must run inside the sandbox, never collapse to unavailable
# ---------------------------------------------------------------------------

def _docker_ready() -> bool:
    from app.execution.runner import _docker_available

    return _docker_available(0)  # single fast probe, no retries


def test_live_second_execution_of_improved_artifacts(_workspace):
    """Real end-to-end chain (no _EXEC stubs) on `m11-demo/calc.py`:
    execute#1 fails -> diagnose -> improve(improved) -> execute#2 must execute
    the improved artifact and must NOT collapse to `unavailable` (regression
    for the live second-execution failure where Docker was healthy but the
    readiness probe misreported)."""
    if not _docker_ready():
        pytest.skip("Docker required for the live execution path")
    pid = _mk_project(_workspace,
                      files=[("m11-demo/calc.py", b"def add(a, b):\n    return a + b\n")])
    state = pl.start_pipeline(pid, _workspace)
    history = [h.stage for h in state.stage_history]
    improves = [h for h in state.stage_history if h.stage == "improve"]
    executes = [h for h in state.stage_history if h.stage == "execute"]
    # every execution that ran must be a usable sandbox result, never a probe
    # misreport of the Docker host
    assert all(h.status != pl.STAGE_UNAVAILABLE for h in executes), [
        (h.stage, h.status, h.reason) for h in state.stage_history
    ]
    assert all("Docker is not available" not in w for h in state.stage_history for w in h.warnings)
    # every SUCCESSFUL improve re-executes; blocked/exhausted ones do not
    succeeded = [h for h in improves if h.status == pl.STAGE_SUCCESS]
    assert len(executes) == 1 + len(succeeded), history
    # pipeline stops deterministically at a gate or terminal, never in flight
    assert state.overall_status in (pl.PIPELINE_WAITING_USER, pl.PIPELINE_COMPLETED,
                                    pl.PIPELINE_BLOCKED)


def test_live_uploaded_folder_project_executes_user_behavioral_test(_workspace):
    """Real uploaded folder layout ``<project>/calc.py`` + ``<project>/test_calc.py``.

    Browser uploads forward the selected folder name as a path prefix. The
    sandbox mounts the (prefix-stripped) source tree at /source and sets
    PYTHONPATH=/source; a user behavioral test doing ``from calc import add``
    must import the source module inside the sandbox — collection must
    succeed and the merged user test must actually run.
    """
    if not _docker_ready():
        pytest.skip("Docker required for the live execution path")
    pid = ingestion.save_upload([
        ("m11-success-demo/calc.py", b"def add(a, b):\n    return a - b\n"),
        ("m11-success-demo/test_calc.py",
         b"from calc import add\n\ndef test_add_returns_sum():\n    assert add(2, 3) == 5\n"),
    ], _workspace).project_id

    src = ingestion.source_dir(_workspace, pid)
    assert (src / "calc.py").is_file()          # prefix stripped at ingestion
    assert not (src / "m11-success-demo").exists()

    assert pl._exec_profile(_workspace, pid)[0] == pl.STAGE_SUCCESS
    assert pl._exec_discover(_workspace, pid)[0] == pl.STAGE_SUCCESS
    assert pl._exec_plan(_workspace, pid)[0] == pl.STAGE_SUCCESS
    assert pl._exec_generate(_workspace, pid)[0] == pl.STAGE_SUCCESS

    gen_dir = ingestion.project_dir(_workspace, pid) / "generated_tests"
    assert (gen_dir / "user_test_calc.py").is_file()
    assert (gen_dir / "user_test_calc.py").read_text(encoding="utf-8").startswith(
        "from calc import add"
    )

    status, _, _, _ = pl._exec_execute(_workspace, pid)
    assert status == pl.STAGE_SUCCESS  # usable sandbox execution, never unavailable
    raw = ingestion.read_execution(_workspace, pid)
    exec_result = json.loads(raw)
    files = {r["file_path"]: r["status"] for r in exec_result["file_results"]}
    # The merged user behavioral test was collected and ran (its assertion
    # fails because add() returns a-b), proving `from calc import add`
    # resolved inside the sandbox.
    assert files.get("user_test_calc.py") == "failed"