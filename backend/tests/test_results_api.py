"""Tests for the read-only results digest API endpoint (Milestone 13)."""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import config
from app.main import app
from app.models.diagnosis import DiagnosisFinding, DiagnosisResult, SourceLocation
from app.models.evaluation import (
    BenchmarkResult,
    CoverageResult,
    EvaluationResult,
    MutationResult,
)
from app.models.execution import ExecutionSummary, TestExecutionResult
from app.models.repair import (
    APPLICATION_APPLIED,
    APPLICATION_NOT_APPLIED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    FINAL_VALIDATION_PASSED,
    FinalValidation,
    RepairCandidate,
    RepairResult,
)
from app.services import project_ingestion as ingestion

client = TestClient(app, raise_server_exceptions=False)


def _ts() -> datetime:
    return datetime.now(timezone.utc)


def _register_project(tmp_path: Path) -> str:
    src = tmp_path / "myproject"
    src.mkdir()
    (src / "app.py").write_text('def add(a, b):\n    return a + b\n', encoding="utf-8")
    (src / "test_app.py").write_text(
        'def test_add():\n    assert 1 + 1 == 2\n', encoding="utf-8")
    resp = client.post("/api/projects/from-path", json={"path": str(src)})
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _write_execution(
    project_id: str,
    status: str,
    test_functions: list[dict] | None = None,
    passed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    total: int = 0,
) -> TestExecutionResult:
    summary = ExecutionSummary(
        total_files=1,
        total_test_functions=total,
        passed=passed,
        failed=failed,
        errors=0,
        skipped=skipped,
    )
    exec_result = TestExecutionResult(
        project_id=project_id,
        overall_status=status,
        exit_code=1 if status == "failed" else 0,
        stdout="",
        summary=summary,
        file_results=[] if test_functions is None else [
            {
                "file_path": "tests/test_app.py",
                "status": "failed" if any(
                    tf["status"] in ("failed", "error") for tf in test_functions
                ) else "passed",
                "stdout": "",
                "stderr": "",
                "test_functions": test_functions,
            }
        ],
    )
    ingestion.save_execution(config.WORKSPACE_DIR, exec_result.model_dump_json())
    return exec_result


def _write_diagnosis(project_id: str, with_traceback: bool = False) -> None:
    finding = DiagnosisFinding(
        finding_id="f1",
        test_file="tests/test_app.py",
        test_function="test_add",
        status="failed",
        failure_signature="sig",
        exception_type="AssertionError",
        message="assert 1 == 2",
        traceback="File /sandbox/secret/path.py:12 ..." if with_traceback else "",
        linked_locations=[SourceLocation(
            source_file="src/app.py", line_start=4, line_end=4,
            qualified_name="app.add",
        )],
        category="assertion",
        severity="high",
        description="test fails",
    )
    result = DiagnosisResult(
        project_id=project_id,
        created_at=_ts(),
        overall_status="failures_diagnosed",
        findings=[finding],
    )
    ingestion.save_diagnosis(config.WORKSPACE_DIR, result.model_dump_json())


def _write_repair(
    project_id: str,
    approval_state: str,
    application_state: str,
    final_status: str = FINAL_VALIDATION_PASSED,
) -> None:
    candidate = RepairCandidate(
        candidate_id="c1",
        file_path="src/app.py",
        source_location="L4-4",
        operation="fix-literal",
        before="return a + b",
        after="return a + b",
        rationale="fix assert",
    )
    result = RepairResult(
        project_id=project_id,
        created_at=_ts(),
        status="validated_pending_approval"
        if approval_state == APPROVAL_PENDING else "approved",
        approval_state=approval_state,
        application_state=application_state,
        selected_candidate=candidate,
        final_validation=FinalValidation(status=final_status),
        reasons=["test reason"],
    )
    ingestion.save_repair(config.WORKSPACE_DIR, result.model_dump_json())


def _write_evaluation(project_id: str) -> None:
    result = EvaluationResult(
        project_id=project_id,
        created_at=_ts(),
        status="completed",
        coverage=CoverageResult(status="completed", line_percentage=80.0),
        mutation=MutationResult(status="completed", mutation_score=60.0),
        benchmark=BenchmarkResult(status="completed", median_seconds=0.5),
    )
    ingestion.save_evaluation(config.WORKSPACE_DIR, result.model_dump_json())


def _meta_files(project_id: str) -> list[str]:
    meta_dir = config.WORKSPACE_DIR / f"{project_id}.meta"
    return sorted(p.name for p in meta_dir.iterdir()) if meta_dir.exists() else []


# ── Digest endpoint tests ────────────────────────────────────────────

class TestResultsEndpoint:
    def test_unknown_project_returns_404(self):
        resp = client.get("/api/projects/nonexistent/results")
        assert resp.status_code == 404

    def test_no_execution_yields_no_execution_verdict(self, tmp_path):
        project_id = _register_project(tmp_path)
        resp = client.get(f"/api/projects/{project_id}/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == project_id
        assert data["overall_verdict"] == "no_execution"
        assert data["execution_status"] is None
        assert data["test_counts"] is None
        assert data["failing_tests"] == []

    def test_passed_execution(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "passed", passed=2, total=2,
                         test_functions=[
                             {"test_function": "test_add", "status": "passed"},
                             {"test_function": "test_sub", "status": "passed"},
                         ])
        resp = client.get(f"/api/projects/{project_id}/results")
        data = resp.json()
        assert data["overall_verdict"] == "passed"
        assert data["execution_status"] == "passed"
        assert data["test_counts"]["passed"] == 2
        assert data["failing_tests"] == []

    def test_failed_execution_falls_back_to_per_test_rows(self, tmp_path):
        """Without diagnosis, failing per-test rows still surface."""
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "failed", passed=1, failed=2, total=3,
                         test_functions=[
                             {"test_function": "test_add", "status": "passed"},
                             {"test_function": "test_div", "status": "failed"},
                             {"test_function": "test_even", "status": "failed"},
                         ])
        resp = client.get(f"/api/projects/{project_id}/results")
        data = resp.json()
        assert data["overall_verdict"] == "failed"
        assert data["test_counts"]["total_test_functions"] == 3
        names = [t["test_function"] for t in data["failing_tests"]]
        assert names == ["test_div", "test_even"]
        assert all(t["exception_type"] == "" for t in data["failing_tests"])

    def test_unavailable_execution(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "unavailable")
        data = client.get(f"/api/projects/{project_id}/results").json()
        assert data["overall_verdict"] == "unavailable"

    def test_diagnosis_enriches_failing_tests(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "failed", failed=1, total=1,
                         test_functions=[
                             {"test_function": "test_add", "status": "failed"},
                         ])
        _write_diagnosis(project_id)
        data = client.get(f"/api/projects/{project_id}/results").json()
        assert data["diagnosis_status"] == "failures_diagnosed"
        ft = data["failing_tests"][0]
        assert ft["test_file"] == "tests/test_app.py"
        assert ft["test_function"] == "test_add"
        assert ft["category"] == "assertion"
        assert ft["severity"] == "high"
        assert ft["exception_type"] == "AssertionError"
        # Source location is project-relative and normalized.
        assert ft["source_file"] == "src/app.py"
        assert ft["source_line_start"] == 4
        assert ft["source_qualified_name"] == "app.add"

    def test_no_tracebacks_or_host_paths_leak(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "failed", failed=1, total=1)
        _write_diagnosis(project_id, with_traceback=True)
        data = client.get(f"/api/projects/{project_id}/results").json()
        raw = json.dumps(data)
        assert "traceback" not in raw
        assert "/sandbox/" not in raw
        assert "host" not in raw.lower()

    def test_repair_applied_and_validated_is_passed(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "failed", failed=1, total=1)
        _write_diagnosis(project_id)
        _write_repair(project_id, "approved", APPLICATION_APPLIED)
        data = client.get(f"/api/projects/{project_id}/results").json()
        assert data["overall_verdict"] == "passed"
        assert data["repair"]["confirmed_repair"] is True
        assert data["repair"]["approval_state"] == "approved"
        assert data["repair"]["selected_file_path"] == "src/app.py"
        assert data["repair"]["reasons"] == ["test reason"]

    def test_repair_pending_approval(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "failed", failed=1, total=1)
        _write_repair(project_id, APPROVAL_PENDING, APPLICATION_NOT_APPLIED)
        data = client.get(f"/api/projects/{project_id}/results").json()
        assert data["overall_verdict"] == "repair_pending"

    def test_repair_rejected(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "failed", failed=1, total=1)
        _write_repair(project_id, APPROVAL_REJECTED, APPLICATION_NOT_APPLIED)
        data = client.get(f"/api/projects/{project_id}/results").json()
        assert data["overall_verdict"] == "rejected"

    def test_evaluation_section(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "passed", passed=2, total=2)
        _write_evaluation(project_id)
        data = client.get(f"/api/projects/{project_id}/results").json()
        ev = data["evaluation"]
        assert ev["status"] == "completed"
        assert ev["coverage_status"] == "completed"
        assert ev["line_coverage_percentage"] == 80.0
        assert ev["mutation_score"] == 60.0
        assert ev["benchmark_median_seconds"] == 0.5

    def test_read_only_get_does_not_write_artifacts(self, tmp_path):
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "passed", passed=2, total=2)
        before = _meta_files(project_id)
        resp = client.get(f"/api/projects/{project_id}/results")
        assert resp.status_code == 200
        after = _meta_files(project_id)
        assert before == after

    def test_response_is_bounded(self, tmp_path):
        """Heavy failure lists are truncated deterministically."""
        project_id = _register_project(tmp_path)
        _write_execution(project_id, "failed", failed=105, total=105,
                         test_functions=[
                             {"test_function": f"test_{i}", "status": "failed"}
                             for i in range(105)
                         ])
        data = client.get(f"/api/projects/{project_id}/results").json()
        assert len(data["failing_tests"]) == 100
        assert any("truncated" in w for w in data["warnings"])