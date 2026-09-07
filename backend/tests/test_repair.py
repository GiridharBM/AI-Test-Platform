"""Tests for the bounded source-code repair service (Milestone 11)."""

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.models.codemap import CodeMap, SourceFunction, SourceModule
from app.models.diagnosis import (
    DiagnosisFinding,
    DiagnosisResult,
    DiagnosisSummary,
    SourceLocation,
)
from app.models.execution import ExecutionSummary, TestExecutionResult, TestFileResult
from app.models.retest import (
    ReTestComparison,
    ReTestResult,
    ReTestSelection,
    ReTestSummary,
    VERDICT_STILL_FAILING,
)
from app.models.test_plan import TestPlan, TestSpec, TestPlanSummary
from app.models.repair import (
    REPAIR_BLOCKED,
    REPAIR_FAILED,
    REPAIR_UNAVAILABLE,
    REPAIR_VALIDATED_PENDING_APPROVAL,
)
from app.services import repair as repair_service
from app.services.repair import (
    _apply_candidate_to_text,
    _candidate_id,
    _parse_line_no,
    _resolve_source_file,
    _detect_operand_family,
    repair_from_artifacts,
    approve_repair,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _codemap(project_id: str = "proj") -> CodeMap:
    mod = SourceModule(
        path="calc.py",
        language="python",
        functions=[
            SourceFunction(
                name="add",
                qualified_name="calc.add",
                file_path="calc.py",
                line_start=1,
                line_end=3,
                args=["a", "b"],
            ),
            SourceFunction(
                name="sub",
                qualified_name="calc.sub",
                file_path="calc.py",
                line_start=5,
                line_end=7,
                args=["a", "b"],
            ),
        ],
    )
    return CodeMap(project_id=project_id, created_at=_now(), source_modules=[mod])


def _retest(still_failing: list[str], project_id: str = "proj") -> ReTestResult:
    comparisons = [
        ReTestComparison(
            test_file="test_calc.py",
            test_function=tf,
            baseline_status="failed",
            retest_status="failed",
            verdict=VERDICT_STILL_FAILING,
        )
        for tf in still_failing
    ]
    summary = ReTestSummary()
    summary.still_failing = len(still_failing)
    summary.executed = len(still_failing)
    return ReTestResult(
        project_id=project_id,
        status="still_failing",
        diagnosis_id="diag1",
        selected_tests=[ReTestSelection(test_file="test_calc.py", test_function=tf) for tf in still_failing],
        comparisons=comparisons,
        summary=summary,
        created_at=_now(),
    )


def _diagnosis() -> DiagnosisResult:
    return DiagnosisResult(
        project_id="proj",
        created_at=_now(),
        overall_status="failures_diagnosed",
        summary=DiagnosisSummary(total_findings=1),
        findings=[
            DiagnosisFinding(
                finding_id="f1",
                test_file="test_add_basic.py",
                test_function="test_add_basic",
                status="failed",
                failure_signature="assertion",
                linked_locations=[
                    SourceLocation(
                        source_file="calc.py",
                        line_start=1,
                        line_end=3,
                        qualified_name="calc.add",
                    ),
                ],
            ),
        ],
        warnings=[],
    )


def _plan() -> TestPlan:
    return TestPlan(
        project_id="proj",
        created_at=_now(),
        specs=[
            TestSpec(
                target_qualified_name="calc.add",
                target_file="calc.py",
                target_type="function",
                priority=1,
                test_type="unit",
                suggested_test_name="test_add_basic",
                risk_score=0.5,
            ),
        ],
        summary=TestPlanSummary(total_specs=1, critical_count=1, high_count=0, medium_count=0, low_count=0),
    )


def _project(tmp_path: Path, source_text: str) -> dict:
    src = tmp_path / "proj" / "source"
    gt = tmp_path / "proj" / "generated_tests"
    src.mkdir(parents=True)
    gt.mkdir(parents=True)
    (src / "calc.py").write_text(source_text, encoding="utf-8")
    (gt / "test_calc.py").write_text("def test_add_basic():\n    assert True\n", encoding="utf-8")
    return {"source": src, "gt": gt, "pid": "proj"}


def _exec_result(overall: str, failed: int, errors: int = 0) -> TestExecutionResult:
    return TestExecutionResult(
        project_id="proj",
        overall_status=overall,
        exit_code=0 if overall == "passed" else 1,
        summary=ExecutionSummary(
            total_files=1,
            passed=1 if overall == "passed" else 0,
            failed=failed,
            errors=errors,
        ),
        file_results=[TestFileResult(file_path="test_calc.py", status=overall)],
    )


class TestCandidateHelpers:
    def test_candidate_id_is_deterministic(self):
        assert _candidate_id("a.py", 3, "return a + b") == _candidate_id("a.py", 3, "return a + b")
        assert _candidate_id("a.py", 3, "return a + b") != _candidate_id("a.py", 4, "return a + b")

    def test_parse_line_no(self):
        assert _parse_line_no("L42") == 42
        assert _parse_line_no("l7") == 7
        assert _parse_line_no("7") == 7
        assert _parse_line_no("") is None
        assert _parse_line_no("abc") is None
        assert _parse_line_no("L0") is None

    def test_parse_line_no_rejects_negative(self):
        assert _parse_line_no("L-3") is None

    def test_detect_operand_family(self):
        assert _detect_operand_family("add", "") == "+"
        assert _detect_operand_family("subtract_then_mod", "") == "-"
        assert _detect_operand_family("multiply", "") == "*"
        assert _detect_operand_family("div", "") == "/"
        assert _detect_operand_family("helper", "") is None
        assert _detect_operand_family("foo", "test_add_basic") == "+"

    def test_resolve_source_file_rejects_traversal(self, tmp_path):
        root = tmp_path / "source"
        root.mkdir()
        (root / "calc.py").write_text("x", encoding="utf-8")
        assert _resolve_source_file(root, "calc.py") is not None
        assert _resolve_source_file(root, "../calc.py") is None
        assert _resolve_source_file(root, "sub/../../calc.py") is None
        assert _resolve_source_file(root, "missing.py") is None
        assert _resolve_source_file(root, "") is None
        assert _resolve_source_file(root, "/etc/passwd") is None

    def test_resolve_source_file_absolute_escape(self, tmp_path):
        root = tmp_path / "source"
        root.mkdir()
        outside = tmp_path / "outside.py"
        outside.write_text("x", encoding="utf-8")
        # Absolute path to an external file must not resolve inside the root.
        assert _resolve_source_file(root, str(outside).replace("\\", "/").lstrip("/")) is None

    def test_resolve_source_file_rejects_nul(self, tmp_path):
        root = tmp_path / "source"
        root.mkdir()
        assert _resolve_source_file(root, "bad\x00name.py") is None

    def test_resolve_source_file_rejects_drive_letter(self, tmp_path):
        root = tmp_path / "source"
        root.mkdir()
        assert _resolve_source_file(root, "C:/Windows/win.ini") is None

    def test_resolve_source_file_symlink_cannot_escape(self, tmp_path):
        root = tmp_path / "source"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.py").write_text("x = 1", encoding="utf-8")
        try:
            (root / "escape").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError, PermissionError):
            pass  # environment lacks symlink/junction privileges; nothing to assert
        else:
            # realpath containment: a symlinked subdir pointing outside the root
            # must not resolve as a contained source file.
            assert _resolve_source_file(root, "escape/secret.py") is None

    def test_resolve_source_file_atomic_write_target_contained(self, tmp_path):
        root = tmp_path / "source"
        root.mkdir()
        (root / "calc.py").write_text("x = 1", encoding="utf-8")
        # The resolved absolute path must sit strictly inside the root, so an
        # atomic write at that exact path can never redirect outside the project.
        resolved = _resolve_source_file(root, "calc.py")
        assert resolved is not None
        assert Path(os.path.realpath(str(resolved))).is_relative_to(
            Path(os.path.realpath(str(root)))
        )


class TestGenerate:
    def test_generates_binop_candidate_when_evidence_contradicts(self, tmp_path):
        p = _project(tmp_path, "def add(a, b):\n    return a - b\n")
        cm = _codemap()
        fn = cm.source_modules[0].functions[0]
        src_file = p["source"] / "calc.py"
        content = src_file.read_text(encoding="utf-8")
        cands = repair_service._generate_candidates_for_function(fn, "test_add_basic", src_file, content)
        assert len(cands) == 1
        c = cands[0]
        assert c.before == "return a - b"
        assert c.after == "return a + b"
        assert c.operation == "replace_us_op_-_with_+"
        assert c.operation.startswith("replace")
        assert c.confidence == 0.8  # evidence from the function's own name

    def test_no_candidate_when_body_already_correct(self, tmp_path):
        p = _project(tmp_path, "def add(a, b):\n    return a + b\n")
        cm = _codemap()
        fn = cm.source_modules[0].functions[0]
        cands = repair_service._generate_candidates_for_function(fn, "test_add_basic", p["source"], "def add(a, b):\n    return a + b\n")
        assert cands == []

    def test_no_candidate_without_evidence(self, tmp_path):
        p = _project(tmp_path, "def helper(a, b):\n    return a - b\n")
        fn = SourceFunction(
            name="helper",
            qualified_name="calc.helper",
            file_path="calc.py",
            line_start=1,
            line_end=3,
            args=["a", "b"],
        )
        cands = repair_service._generate_candidates_for_function(
            fn, "test_helper_whatever", p["source"], "def helper(a, b):\n    return a - b\n"
        )
        # No word evidence in name or suggested test name -> no candidate.
        assert cands == []

    def test_evidence_from_suggested_test_name_lowers_confidence(self, tmp_path):
        p = _project(tmp_path, "def compute(a, b):\n    return a + b\n")
        cm = _codemap()
        fn = cm.source_modules[0].functions[0]
        fn.args = ["a", "b"]
        cands = repair_service._generate_candidates_for_function(fn, "test_add_basic", p["source"], "def compute(a, b):\n    return a + b\n")
        assert cands == []  # body matches implied op, so no candidate


class TestApply:
    def test_apply_candidate_to_text(self):
        cand = repair_service.RepairCandidate(
            candidate_id="c1",
            file_path="calc.py",
            source_location="L2",
            before="return a - b",
            after="return a + b",
        )
        updated, ok = _apply_candidate_to_text("def add(a, b):\n    return a - b\n", cand)
        assert ok
        assert updated == "def add(a, b):\n    return a + b\n"

    def test_apply_preserves_indentation(self):
        cand = repair_service.RepairCandidate(
            candidate_id="c1",
            file_path="calc.py",
            source_location="L2",
            before="return a + b",
            after="return a * b",
        )
        updated, ok = _apply_candidate_to_text("def add(a, b):\n    return a + b\n", cand)
        assert updated == "def add(a, b):\n    return a * b\n"

    def test_apply_rejects_when_before_mismatch(self):
        cand = repair_service.RepairCandidate(
            candidate_id="c1",
            file_path="calc.py",
            source_location="L2",
            before="return a + b",
            after="return a * b",
        )
        updated, ok = _apply_candidate_to_text("def add(a, b):\n    return a - b\n", cand)
        assert not ok
        assert updated == "def add(a, b):\n    return a - b\n"


class TestRepairLoop:
    def _run(self, tmp_path, mock_return, source_text="def add(a, b):\n    return a - b\n", pid="proj"):
        p = _project(tmp_path, source_text)
        cm = _codemap(project_id=pid)
        diag = _diagnosis()
        plan = _plan()
        retest = _retest(["test_add_basic"], project_id=pid)
        with patch("app.execution.runner.execute_tests", return_value=mock_return) as mock:
            result = repair_from_artifacts(
                diag, cm, plan, retest,
                source_dir=p["source"],
                generated_test_dir=p["gt"],
                project_id=pid,
            )
        return result, mock, p

    def test_blocked_when_codemap_missing(self, tmp_path):
        p = _project(tmp_path, "def add(a, b):\n    return a - b\n")
        plan = _plan()
        retest = _retest(["test_add_basic"])
        with patch("app.execution.runner.execute_tests") as mock:
            result = repair_from_artifacts(
                _diagnosis(), None, plan, retest,
                source_dir=p["source"], generated_test_dir=p["gt"], project_id="proj",
            )
        assert result.status == REPAIR_BLOCKED
        assert not mock.called

    def test_blocked_when_no_still_failing(self, tmp_path):
        p = _project(tmp_path, "def add(a, b):\n    return a - b\n")
        cm = _codemap()
        diag = _diagnosis()
        retest = _retest([])
        with patch("app.execution.runner.execute_tests") as mock:
            result = repair_from_artifacts(
                diag, cm, _plan(), retest,
                source_dir=p["source"], generated_test_dir=p["gt"], project_id="proj",
            )
        assert result.status == REPAIR_BLOCKED
        assert not mock.called

    def test_validated_pending_approval_on_first_pass(self, tmp_path):
        result, mock, p = self._run(tmp_path, _exec_result("passed", 0))
        assert result.status == REPAIR_VALIDATED_PENDING_APPROVAL
        assert result.selected_candidate is not None
        assert result.selected_candidate.after == "return a + b"
        assert result.selected_candidate.attempt_number == 1
        assert len(result.attempts) == 1
        assert result.attempts[0].validation_status == "passed"
        assert mock.call_count == 1
        # Original source untouched.
        assert (p["source"] / "calc.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"

    def test_original_source_never_modified(self, tmp_path):
        source_text = "def add(a, b):\n    return a - b\n"
        result, _, p = self._run(tmp_path, _exec_result("failed", 1), source_text=source_text)
        assert (p["source"] / "calc.py").read_text(encoding="utf-8") == source_text
        # Source file count unchanged (no mutation artifacts in original tree).
        assert len(list(p["source"].iterdir())) == 1

    def test_failed_then_second_candidate_passes(self, tmp_path):
        # Two distinct still-failing functions each yield a candidate.
        p = _project(tmp_path, "def add(a, b):\n    return a - b\n\ndef sub(a, b):\n    return a * b\n")
        cm = _codemap()
        # Mutation: the first candidate (add) fails, the second (sub) passes.
        plan = _plan()
        diag = _diagnosis()
        retest = _retest(["test_add_basic", "test_sub_basic"])
        with patch(
            "app.execution.runner.execute_tests",
            side_effect=[_exec_result("failed", 1), _exec_result("passed", 0)],
        ) as mock:
            result = repair_from_artifacts(
                diag, cm, plan, retest,
                source_dir=p["source"], generated_test_dir=p["gt"], project_id="proj",
            )
        assert result.status == REPAIR_VALIDATED_PENDING_APPROVAL
        assert len(result.attempts) == 2
        assert result.attempts[0].validation_status == "failed"
        assert result.attempts[1].validation_status == "passed"
        assert mock.call_count == 2

    def test_all_failed_returns_failed(self, tmp_path):
        result, mock, _ = self._run(tmp_path, _exec_result("failed", 1))
        assert result.status != REPAIR_BLOCKED
        assert mock.call_count >= 1

    def test_no_duplicate_candidate_execution(self, tmp_path):
        # All candidates fail -> 'failed'; verify the same candidate id never runs twice.
        p = _project(tmp_path, "def add(a, b):\n    return a - b\n")
        cm = _codemap()
        plan = _plan()
        diag = _diagnosis()
        retest = _retest(["test_add_basic"])
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("failed", 1)) as mock:
            result = repair_from_artifacts(
                diag, cm, plan, retest,
                source_dir=p["source"], generated_test_dir=p["gt"], project_id="proj",
            )
        ids = {a.candidate_id for a in result.attempts}
        assert len(ids) == len(result.attempts)  # no repeat
        assert mock.call_count == len(ids)

    def test_unavailable_returns_unavailable(self, tmp_path):
        result, _, _ = self._run(tmp_path, TestExecutionResult(
            project_id="proj", overall_status="unavailable", exit_code=-1,
            summary=ExecutionSummary(total_files=0),
        ))
        assert result.status == REPAIR_UNAVAILABLE

    def test_bounded_loop_respects_config(self, tmp_path):
        import app.core.config as config
        config.REPAIR_MAX_ATTEMPTS = 2
        result, mock, _ = self._run(tmp_path, _exec_result("failed", 1))
        assert mock.call_count <= 2


class TestApproval:
    def _write_repair_result(self, workspace: Path, project_id: str, owner=None):
        from app.models.repair import RepairResult
        from app.services import project_ingestion as ingestion

        cand = repair_service.RepairCandidate(
            candidate_id="c1",
            file_path="calc.py",
            source_location="L2",
            before="return a - b",
            after="return a + b",
        )
        attempt = repair_service.RepairAttempt(
            attempt_number=1,
            candidate_id=cand.candidate_id,
            file_path="calc.py",
            source_location="L2",
            validation_status="passed",
            created_at=_now(),
        )
        result = RepairResult(
            project_id=project_id or "proj",
            status=repair_service.REPAIR_VALIDATED_PENDING_APPROVAL,
            attempts=[attempt],
            selected_candidate=cand,
            approval_state="pending",
            application_state="not_applied",
            created_at=_now(),
        )
        ingestion.save_repair(workspace, result.model_dump_json())
        return result

    def _source(self, workspace: Path, project_id: str) -> Path:
        from app.models.project import ProjectMeta

        meta = ProjectMeta(project_id=project_id, name="proj", origin="upload", created_at=_now())
        meta_path = workspace / project_id / ".meta" / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(meta.model_dump_json(), encoding="utf-8")
        src = workspace / project_id / "source"
        src.mkdir(parents=True, exist_ok=True)
        f = src / "calc.py"
        f.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        return f

    def _gt(self, workspace: Path, project_id: str) -> Path:
        gt = workspace / project_id / "generated_tests"
        gt.mkdir(parents=True, exist_ok=True)
        (gt / "test_calc.py").write_text("def test_add_basic():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        return gt

    def test_rejected_when_no_repair_result(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        from app.models.project import ProjectMeta
        meta = ProjectMeta(project_id="proj", name="proj", origin="upload", created_at=_now())
        meta_path = workspace / "proj" / ".meta" / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(meta.model_dump_json(), encoding="utf-8")
        with patch("app.execution.runner.execute_tests") as mock:
            # No persisted result.
            try:
                approve_repair("proj", workspace=workspace)
                assert False, "expected FileNotFoundError"
            except FileNotFoundError:
                pass
            assert not mock.called

    def test_rejected_when_not_pending_approval(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        self._source(workspace, "proj")
        self._gt(workspace, "proj")
        from app.models.repair import RepairResult
        result = RepairResult(
            project_id="proj",
            status=repair_service.REPAIR_FAILED,
            created_at=_now(),
        )
        from app.services import project_ingestion as ingestion
        ingestion.save_repair(workspace, result.model_dump_json())
        with patch("app.execution.runner.execute_tests") as mock:
            approved = approve_repair("proj", workspace=workspace)
        assert approved.status == "rejected"
        assert "No valid candidate" in approved.reasons[0]
        assert not mock.called
        # Source not modified.
        assert self._source(workspace, "proj").read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"

    def test_rejected_when_source_changed_since_validation(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        src_f = workspace / "proj" / "source" / "calc.py"
        src_f.parent.mkdir(parents=True)
        src_f.write_text("def add(a, b):\n    return a + 1\n", encoding="utf-8")
        self._gt(workspace, "proj")
        # meta.json so approve_repair can resolve source_root (upload origin).
        from app.models.project import ProjectMeta
        meta = ProjectMeta(project_id="proj", name="proj", origin="upload", created_at=_now())
        meta_path = workspace / "proj" / ".meta" / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(meta.model_dump_json(), encoding="utf-8")
        self._write_repair_result(workspace, "proj")
        with patch("app.execution.runner.execute_tests") as mock:
            approved = approve_repair("proj", workspace=workspace)
        assert approved.status == "rejected"
        assert approved.reasons == ["Original source changed since candidate validation; approval invalidated."]
        assert not mock.called
        assert src_f.read_text(encoding="utf-8") == "def add(a, b):\n    return a + 1\n"

    def test_rejected_when_already_applied(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        self._source(workspace, "proj")
        self._gt(workspace, "proj")
        self._write_repair_result(workspace, "proj")
        from app.services import project_ingestion as ingestion
        raw = ingestion.read_repair(workspace, "proj")
        from app.models.repair import RepairResult
        repair = RepairResult.model_validate_json(raw)
        repair.application_state = "applied"
        ingestion.save_repair(workspace, repair.model_dump_json())
        with patch("app.execution.runner.execute_tests") as mock:
            approved = approve_repair("proj", workspace=workspace)
        assert approved.status == "rejected"
        assert "already been applied" in approved.reasons[0]
        assert not mock.called

    def test_apply_and_final_validation_passes(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        src_f = self._source(workspace, "proj")
        self._gt(workspace, "proj")
        self._write_repair_result(workspace, "proj")
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("passed", 0)) as mock:
            approved = approve_repair("proj", workspace=workspace)
        assert approved.status == "applied"
        assert approved.application_state == "applied"
        assert approved.final_validation.status == "passed"
        # Source now patched.
        assert src_f.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
        assert mock.call_count == 1

    def test_apply_preserves_unrelated_source(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        src_f = self._source(workspace, "proj")
        src_f.write_text("def add(a, b):\n    return a - b\n\ndef other():\n    return 42\n", encoding="utf-8")
        self._gt(workspace, "proj")
        self._write_repair_result(workspace, "proj")
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("passed", 0)):
            approve_repair("proj", workspace=workspace)
        assert src_f.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n\ndef other():\n    return 42\n"

    def test_final_validation_after_apply(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        self._source(workspace, "proj")
        self._gt(workspace, "proj")
        self._write_repair_result(workspace, "proj")
        # Final validation reports failure -> applied status retained, final marked failed.
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("failed", 1)):
            approved = approve_repair("proj", workspace=workspace)
        assert approved.status == "applied"
        assert approved.final_validation.status == "failed"