"""Tests for the deterministic re-test service (Milestone 9)."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.core import config
from app.models.diagnosis import DiagnosisFinding, DiagnosisResult
from app.models.execution import (
    ExecutionSummary,
    TestExecutionResult,
    TestFileResult,
)
from app.models.improvement import ImprovementChange, ImprovementResult
from app.models.retest import (
    RETEST_BLOCKED,
    RETEST_FIXED,
    RETEST_NO_OP,
    RETEST_PASSED,
    RETEST_REGRESSION,
    RETEST_STILL_FAILING,
    RETEST_UNAVAILABLE,
    VERDICT_BLOCKED,
    VERDICT_FIXED,
    VERDICT_PASSED,
    VERDICT_REGRESSION,
    VERDICT_STILL_FAILING,
    ReTestComparison,
    ReTestResult,
)
from app.services.retest import (
    _build_baseline_function_map,
    _build_baseline_status_map,
    _derive_file_retest_status,
    _derive_verdict,
    _select_improved_tests,
    _select_user_behavioral_tests,
    retest_from_artifacts,
)
import app.services.retest as retest_service

_CREATED = datetime.now(timezone.utc)


def _improvement(
    status="improved",
    changes=None,
    diagnosis_id="diag123",
):
    return ImprovementResult(
        project_id="p1",
        created_at=_CREATED,
        status=status,
        diagnosis_id=diagnosis_id,
        changes=changes or [],
        files_modified=1,
    )


def _change(
    test_file="test_app.py",
    test_func="test_add",
    status="improved",
):
    return ImprovementChange(
        finding_id="f1",
        test_file=test_file,
        test_function=test_func,
        status=status,
    )


def _diagnosis(findings=None):
    return DiagnosisResult(
        project_id="p1",
        created_at=_CREATED,
        overall_status="failures_diagnosed",
        findings=findings or [],
    )


def _finding(fid="f1", test_file="test_app.py", test_func="test_add", status="failed"):
    return DiagnosisFinding(
        finding_id=fid,
        test_file=test_file,
        test_function=test_func,
        status=status,
        failure_signature="sig",
        exception_type="NotImplementedError",
        category="exception",
    )


def _prev_exec(file_results=None):
    return TestExecutionResult(
        project_id="p1",
        overall_status="failed",
        exit_code=1,
        summary=ExecutionSummary(total_files=1, passed=0, failed=1),
        file_results=file_results or [],
    )


def _retest_exec(file_results=None):
    return TestExecutionResult(
        project_id="p1",
        overall_status="passed",
        exit_code=0,
        summary=ExecutionSummary(total_files=1, passed=1, failed=0),
        file_results=file_results or [],
    )


class TestSelectImprovedTests:
    def test_selects_only_improved(self):
        imp = _improvement(changes=[
            _change(status="improved"),
            _change(status="blocked"),
            _change(status="no_change"),
        ])
        selected = _select_improved_tests(imp)
        assert len(selected) == 1
        assert selected[0].test_function == "test_add"

    def test_no_improved_returns_empty(self):
        imp = _improvement(changes=[_change(status="blocked")])
        assert _select_improved_tests(imp) == []

    def test_deduplicates_by_file_function(self):
        imp = _improvement(changes=[
            _change(status="improved"),
            _change(status="improved"),
        ])
        selected = _select_improved_tests(imp)
        assert len(selected) == 1

    def test_multiple_functions(self):
        imp = _improvement(changes=[
            _change(test_func="test_a", status="improved"),
            _change(test_func="test_b", status="improved"),
        ])
        selected = _select_improved_tests(imp)
        assert len(selected) == 2
        funcs = {s.test_function for s in selected}
        assert funcs == {"test_a", "test_b"}


class TestBaselineMaps:
    def test_build_status_map(self):
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
            TestFileResult(file_path="test_other.py", status="passed"),
        ])
        m = _build_baseline_status_map(prev)
        assert m["test_app.py"] == "failed"
        assert m["test_other.py"] == "passed"

    def test_build_status_map_none(self):
        assert _build_baseline_status_map(None) == {}

    def test_build_function_map(self):
        diag = _diagnosis(findings=[
            _finding(status="failed"),
            _finding(fid="f2", test_func="test_other", status="error"),
        ])
        m = _build_baseline_function_map(diag)
        assert m[("test_app.py", "test_add")] == "failed"
        assert m[("test_app.py", "test_other")] == "error"

    def test_build_function_map_none(self):
        assert _build_baseline_function_map(None) == {}


class TestDeriveVerdict:
    def test_fixed_from_failed(self):
        v, r = _derive_verdict("failed", "passed", "failed")
        assert v == VERDICT_FIXED
        assert "passes" in r

    def test_still_failing(self):
        v, r = _derive_verdict("failed", "failed", "failed")
        assert v == VERDICT_STILL_FAILING
        assert "still" in r

    def test_regression(self):
        v, r = _derive_verdict("passed", "failed", "")
        assert v == VERDICT_REGRESSION
        assert "previously passing" in r.lower()

    def test_passed_without_prior_failure(self):
        v, r = _derive_verdict("passed", "passed", "")
        assert v == VERDICT_PASSED

    def test_no_baseline_passes(self):
        v, _ = _derive_verdict("", "passed", "")
        assert v == VERDICT_BLOCKED

    def test_no_baseline_fails_blocked(self):
        v, _ = _derive_verdict("", "failed", "")
        assert v == VERDICT_BLOCKED

    def test_unavailable_retest(self):
        from app.models.retest import VERDICT_UNAVAILABLE
        v, _ = _derive_verdict("failed", "unavailable", "")
        assert v == VERDICT_UNAVAILABLE

    def test_no_retest_status_blocked(self):
        v, _ = _derive_verdict("failed", "", "")
        assert v == VERDICT_BLOCKED

    def test_timeout_retest_blocked(self):
        v, _ = _derive_verdict("failed", "timeout", "")
        assert v == VERDICT_BLOCKED

    def test_fixed_from_error(self):
        v, _ = _derive_verdict("error", "passed", "error")
        assert v == VERDICT_FIXED

    def test_still_failing_from_error(self):
        v, _ = _derive_verdict("error", "error", "error")
        assert v == VERDICT_STILL_FAILING


class TestDeriveFileRetestStatus:
    def test_found(self):
        exec_result = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])
        assert _derive_file_retest_status(exec_result, "test_app.py") == "passed"

    def test_not_found(self):
        exec_result = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])
        assert _derive_file_retest_status(exec_result, "test_other.py") == ""


class TestRetestFromArtifacts:
    def test_no_op_when_improvement_no_change(self):
        imp = _improvement(status="no_change")
        result = retest_from_artifacts(imp, None, None, project_id="p1")
        assert result.status == RETEST_NO_OP
        assert len(result.selected_tests) == 0
        assert any("nothing to re-test" in r.lower() for r in result.reasons)

    def test_no_op_when_improvement_blocked(self):
        imp = _improvement(status="blocked")
        result = retest_from_artifacts(imp, None, None, project_id="p1")
        assert result.status == RETEST_NO_OP

    def test_no_op_when_no_improved_changes(self):
        imp = _improvement(status="partial", changes=[_change(status="blocked")])
        result = retest_from_artifacts(imp, None, None, project_id="p1")
        assert result.status == RETEST_NO_OP
        assert any("no changes" in r.lower() for r in result.reasons)

    def test_blocked_when_generated_tests_missing(self, tmp_path):
        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        result = retest_from_artifacts(imp, diag, prev, gen_root=tmp_path, project_id="p1")
        assert result.status == RETEST_BLOCKED
        assert any("not found" in r.lower() for r in result.reasons)

    def test_blocked_when_diagnosis_missing(self, tmp_path):
        pid = "p-nodiag"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")
        imp = _improvement(changes=[_change(status="improved")])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        with patch("app.execution.runner.execute_tests") as mock:
            result = retest_from_artifacts(imp, None, prev, gen_root=tmp_path, project_id=pid)
        assert result.status == RETEST_BLOCKED
        assert not mock.called
        assert any("diagnosis" in w.lower() for w in result.warnings)
        assert len(result.comparisons) == 0

    def test_blocked_when_prev_execution_missing(self, tmp_path):
        pid = "p-noexec"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")
        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        with patch("app.execution.runner.execute_tests") as mock:
            result = retest_from_artifacts(imp, diag, None, gen_root=tmp_path, project_id=pid)
        assert result.status == RETEST_BLOCKED
        assert not mock.called
        assert any("execution" in w.lower() for w in result.warnings)
        assert len(result.comparisons) == 0

    def test_blocked_when_both_missing(self, tmp_path):
        pid = "p-noboth"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")
        imp = _improvement(changes=[_change(status="improved")])
        with patch("app.execution.runner.execute_tests") as mock:
            result = retest_from_artifacts(imp, None, None, gen_root=tmp_path, project_id=pid)
        assert result.status == RETEST_BLOCKED
        assert not mock.called
        assert len(result.warnings) == 1
        assert "diagnosis" in result.warnings[0].lower()
        assert "execution" in result.warnings[0].lower()
        assert len(result.comparisons) == 0

    def test_fixed_when_previously_failing_now_passing(self, tmp_path):
        pid = "p-fixed"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")], diagnosis_id="d1")
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest):
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )
        assert result.status == RETEST_FIXED
        assert len(result.comparisons) == 1
        assert result.comparisons[0].verdict == VERDICT_FIXED
        assert result.summary.fixed == 1

    def test_still_failing(self, tmp_path):
        pid = "p-still"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest):
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )
        assert result.status == RETEST_STILL_FAILING
        assert result.comparisons[0].verdict == VERDICT_STILL_FAILING

    def test_regression(self, tmp_path):
        pid = "p-regress"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        # No diagnosis finding for this function — true regression scenario.
        diag = _diagnosis(findings=[])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest):
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )
        assert result.status == RETEST_REGRESSION
        assert result.comparisons[0].verdict == VERDICT_REGRESSION

    def test_passed_without_prior_failure(self, tmp_path):
        pid = "p-passed"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest):
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )
        assert result.status == RETEST_PASSED
        assert result.comparisons[0].verdict == VERDICT_PASSED

    def test_unavailable_docker(self, tmp_path):
        pid = "p-unavail"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        unavail = TestExecutionResult(
            project_id=pid,
            overall_status="unavailable",
            exit_code=-1,
        )

        with patch("app.execution.runner.execute_tests", return_value=unavail):
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )
        assert result.status == RETEST_UNAVAILABLE

    def test_no_m8_reinvocation(self, tmp_path):
        """Verify retest does not invoke improvement."""
        pid = "p-noloop"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest) as mock_exec:
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )
        # execute_tests called once (re-test), no improvement invoked
        assert mock_exec.call_count == 1
        assert result.status in (RETEST_PASSED, RETEST_FIXED)

    def test_source_remains_untouched(self, tmp_path):
        pid = "p-safe"
        src = tmp_path / pid / "source" / "app.py"
        src.parent.mkdir(parents=True)
        src.write_text("def add(a, b): return a + b", encoding="utf-8")
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest):
            retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )
        assert src.read_text(encoding="utf-8") == "def add(a, b): return a + b"

    def test_deterministic_repeated_result(self, tmp_path):
        pid = "p-det"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest):
            r1 = retest_from_artifacts(imp, diag, prev, gen_root=tmp_path, project_id=pid)
            r2 = retest_from_artifacts(imp, diag, prev, gen_root=tmp_path, project_id=pid)
        assert r1.status == r2.status
        assert r1.comparisons[0].verdict == r2.comparisons[0].verdict

    def test_meta_write_boundary(self, tmp_path):
        pid = "p-boundary"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "test_app.py").write_text("def test_add(): pass", encoding="utf-8")

        imp = _improvement(changes=[_change(status="improved")])
        diag = _diagnosis(findings=[_finding()])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="test_app.py", status="passed"),
        ])

        with patch("app.execution.runner.execute_tests", return_value=retest):
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid
            )

        # Only .meta/retest.json should be writable; nothing else modified.
        generated = (gt / "test_app.py").read_text(encoding="utf-8")
        assert generated == "def test_add(): pass"  # retest doesn't modify tests


class TestUserBehavioralSelection:
    def test_selects_failing_user_tests_from_copied_files(self):
        diag = _diagnosis(findings=[
            _finding(test_file="user_test_calc.py", test_func="test_add_returns_sum"),
            _finding(fid="f2", test_file="user_test_calc.py", test_func="test_sub_works"),
        ])
        selected = retest_service._select_user_behavioral_tests(
            diag, ["user_test_calc.py"]
        )
        assert {s.test_function for s in selected} == {"test_add_returns_sum", "test_sub_works"}
        assert selected[0].improvement_status == "user_behavioral"

    def test_ignores_unrelated_and_unmerged_files(self):
        diag = _diagnosis(findings=[
            _finding(test_file="user_test_calc.py", test_func="test_add_returns_sum"),
            _finding(fid="f2", test_file="test_calc.py", test_func="test_generated"),
        ])
        sel = retest_service._select_user_behavioral_tests(diag, ["user_test_calc.py"])
        assert [s.test_function for s in sel] == ["test_add_returns_sum"]
        assert retest_service._select_user_behavioral_tests(diag, None) == []
        assert retest_service._select_user_behavioral_tests(None, ["user_test_calc.py"]) == []

    def test_deduplicates_findings(self):
        diag = _diagnosis(findings=[
            _finding(test_file="user_test_calc.py", test_func="test_add_returns_sum"),
            _finding(fid="f2", test_file="user_test_calc.py", test_func="test_add_returns_sum"),
        ])
        selected = retest_service._select_user_behavioral_tests(diag, ["user_test_calc.py"])
        assert len(selected) == 1

    def test_still_failing_user_behavioral_survives_blocked_improvement(self, tmp_path):
        """A BLOCKED improvement must NOT collapse to NO_OP while a merged user
        behavioral test is still failing — M11 needs its still-failing verdict.
        Regression: the pre-fix fast-path returned no-op for any blocked M8."""
        pid = "p-userblocked"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "user_test_calc.py").write_text("def test_add_returns_sum():\n    assert add(2, 3) == 5\n", encoding="utf-8")

        imp = _improvement(status="blocked")
        diag = _diagnosis(findings=[
            _finding(test_file="user_test_calc.py", test_func="test_add_returns_sum"),
        ])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="user_test_calc.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="user_test_calc.py", status="failed"),
        ])
        with patch("app.execution.runner.execute_tests", return_value=retest) as mock:
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid,
                copied_user_tests=["user_test_calc.py"],
            )
        assert mock.called
        assert result.status == RETEST_STILL_FAILING
        assert len(result.comparisons) == 1
        assert result.comparisons[0].test_function == "test_add_returns_sum"
        assert result.comparisons[0].verdict == VERDICT_STILL_FAILING
        assert result.summary.still_failing == 1

    def test_user_behavioral_fixed_when_now_passing(self, tmp_path):
        """A formerly-failing user behavioral test that now passes reports fixed."""
        pid = "p-userfixed"
        gt = tmp_path / pid / "generated_tests"
        gt.mkdir(parents=True)
        (gt / "user_test_calc.py").write_text("def test_add_returns_sum():\n    assert add(2, 3) == 5\n", encoding="utf-8")

        imp = _improvement(status="blocked")
        diag = _diagnosis(findings=[
            _finding(test_file="user_test_calc.py", test_func="test_add_returns_sum"),
        ])
        prev = _prev_exec(file_results=[
            TestFileResult(file_path="user_test_calc.py", status="failed"),
        ])
        retest = _retest_exec(file_results=[
            TestFileResult(file_path="user_test_calc.py", status="passed"),
        ])
        with patch("app.execution.runner.execute_tests", return_value=retest):
            result = retest_from_artifacts(
                imp, diag, prev, gen_root=tmp_path, project_id=pid,
                copied_user_tests=["user_test_calc.py"],
            )
        assert result.status == RETEST_FIXED
        assert result.comparisons[0].verdict == VERDICT_FIXED

    def test_no_op_still_returned_when_user_tests_absent(self, tmp_path):
        """Without copied user tests the blocked/no_change fast-path is preserved."""
        imp = _improvement(status="blocked")
        result = retest_from_artifacts(
            imp, _diagnosis(findings=[_finding()]), None,
            gen_root=tmp_path, project_id="p1", copied_user_tests=[],
        )
        assert result.status == RETEST_NO_OP


class TestRetestResultModel:
    def test_schema_version(self):
        r = ReTestResult(project_id="p", created_at=_CREATED)
        assert r.schema_version == 1

    def test_default_status(self):
        r = ReTestResult(project_id="p", created_at=_CREATED)
        assert r.status == RETEST_NO_OP

    def test_all_verdicts_valid(self):
        from app.models.retest import VALID_VERDICTS
        assert VERDICT_FIXED in VALID_VERDICTS
        assert VERDICT_STILL_FAILING in VALID_VERDICTS
        assert VERDICT_REGRESSION in VALID_VERDICTS
        assert VERDICT_PASSED in VALID_VERDICTS
        assert VERDICT_BLOCKED in VALID_VERDICTS
