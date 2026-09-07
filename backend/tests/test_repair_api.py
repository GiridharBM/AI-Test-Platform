"""Tests for the repair API endpoints and GET project integration (Milestone 11)."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import config
from app.main import app
from app.models.codemap import CodeMap, SourceFunction, SourceModule
from app.models.diagnosis import DiagnosisFinding, DiagnosisResult, DiagnosisSummary, SourceLocation
from app.models.execution import ExecutionSummary, TestExecutionResult, TestFileResult
from app.models.project import ProjectMeta
from app.models.retest import (
    ReTestComparison,
    ReTestResult,
    ReTestSelection,
    ReTestSummary,
    VERDICT_STILL_FAILING,
)
from app.models.test_plan import TestPlan, TestPlanSummary, TestSpec
from app.services import project_ingestion as ingestion

client = TestClient(app, raise_server_exceptions=False)

NOW = datetime.now(timezone.utc)


def _register_project(tmp_path: Path) -> str:
    src = tmp_path / "myproject"
    src.mkdir()
    (src / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    resp = client.post("/api/projects/from-path", json={"path": str(src)})
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _write_meta(project_id: str, *, origin: str = "upload", source_path: str = "") -> None:
    meta = ProjectMeta(
        project_id=project_id,
        name="proj",
        origin=origin,
        source_path=source_path or str(config.WORKSPACE_DIR / project_id / "source"),
        created_at=NOW,
    )
    _meta_path = Path(config.WORKSPACE_DIR) / project_id / ".meta" / "meta.json"
    _meta_path.parent.mkdir(parents=True, exist_ok=True)
    _meta_path.write_text(meta.model_dump_json(), encoding="utf-8")


def _write_source(project_id: str, content: str) -> Path:
    src = Path(config.WORKSPACE_DIR) / project_id / "source"
    src.mkdir(parents=True, exist_ok=True)
    f = src / "calc.py"
    f.write_text(content, encoding="utf-8")
    return f


def _write_codemap(project_id: str) -> None:
    cm = CodeMap(
        project_id=project_id,
        created_at=NOW,
        source_modules=[
            SourceModule(
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
                ],
            ),
        ],
    )
    ingestion.save_codemap(config.WORKSPACE_DIR, cm.model_dump_json())


def _write_test_plan(project_id: str) -> None:
    plan = TestPlan(
        project_id=project_id,
        created_at=NOW,
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
    ingestion.save_test_plan(config.WORKSPACE_DIR, plan.model_dump_json())


def _write_diagnosis(project_id: str) -> None:
    diag = DiagnosisResult(
        project_id=project_id,
        created_at=NOW,
        overall_status="failures_diagnosed",
        summary=DiagnosisSummary(total_findings=1),
        findings=[
            DiagnosisFinding(
                finding_id="f1",
                test_file="test_calc.py",
                test_function="test_add_basic",
                status="failed",
                failure_signature="assertion",
            ),
        ],
    )
    ingestion.save_diagnosis(config.WORKSPACE_DIR, diag.model_dump_json())


def _write_retest(project_id: str, still_failing: list[str]) -> None:
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
    retest = ReTestResult(
        project_id=project_id,
        status="still_failing",
        diagnosis_id="diag1",
        selected_tests=[ReTestSelection(test_file="test_calc.py", test_function=tf) for tf in still_failing],
        comparisons=comparisons,
        summary=summary,
        created_at=NOW,
    )
    ingestion.save_retest(config.WORKSPACE_DIR, retest.model_dump_json())


def _write_gt(project_id: str) -> Path:
    gt = Path(config.WORKSPACE_DIR) / project_id / "generated_tests"
    gt.mkdir(parents=True, exist_ok=True)
    (gt / "test_calc.py").write_text("def test_add_basic():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    return gt


def _exec_result(overall: str, failed: int) -> TestExecutionResult:
    return TestExecutionResult(
        project_id="proj",
        overall_status=overall,
        exit_code=0 if overall == "passed" else 1,
        summary=ExecutionSummary(total_files=1, passed=1 if overall == "passed" else 0, failed=failed),
        file_results=[TestFileResult(file_path="test_calc.py", status=overall)],
    )


class TestRepairEndpoint:
    def test_project_not_found_returns_404(self):
        resp = client.post("/api/projects/nonexistent/repair")
        assert resp.status_code == 404

    def test_no_retest_returns_422(self, tmp_path):
        pid = _register_project(tmp_path)
        _write_meta(pid)
        _write_source(pid, "def add(a, b):\n    return a - b\n")
        _write_codemap(pid)
        _write_diagnosis(pid)
        resp = client.post(f"/api/projects/{pid}/repair")
        assert resp.status_code == 422

    def test_validated_pending_approval(self, tmp_path):
        pid = _register_project(tmp_path)
        _write_meta(pid)
        _write_source(pid, "def add(a, b):\n    return a - b\n")
        _write_gt(pid)
        _write_codemap(pid)
        _write_test_plan(pid)
        _write_diagnosis(pid)
        _write_retest(pid, ["test_add_basic"])
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("passed", 0)):
            resp = client.post(f"/api/projects/{pid}/repair")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "validated_pending_approval"
        assert body["selected_candidate"]["after"] == "return a + b"
        assert body["application_state"] == "not_applied"

    def test_blocked_when_no_still_failing(self, tmp_path):
        pid = _register_project(tmp_path)
        _write_meta(pid)
        _write_source(pid, "def add(a, b):\n    return a - b\n")
        _write_gt(pid)
        _write_codemap(pid)
        _write_test_plan(pid)
        _write_diagnosis(pid)
        _write_retest(pid, [])
        resp = client.post(f"/api/projects/{pid}/repair")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "blocked"

    def test_original_source_not_modified(self, tmp_path):
        pid = _register_project(tmp_path)
        _write_meta(pid)
        src_f = _write_source(pid, "def add(a, b):\n    return a - b\n")
        _write_gt(pid)
        _write_codemap(pid)
        _write_diagnosis(pid)
        _write_retest(pid, ["test_add_basic"])
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("passed", 0)):
            client.post(f"/api/projects/{pid}/repair")
        assert src_f.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"


class TestRepairApproveEndpoint:
    def test_no_repair_returns_422(self, tmp_path):
        pid = _register_project(tmp_path)
        _write_meta(pid)
        resp = client.post(f"/api/projects/{pid}/repair/approve")
        assert resp.status_code == 422

    def test_approve_applies_candidate(self, tmp_path):
        pid = _register_project(tmp_path)
        _write_meta(pid)
        src_f = _write_source(pid, "def add(a, b):\n    return a - b\n")
        _write_gt(pid)
        _write_codemap(pid)
        _write_test_plan(pid)
        _write_diagnosis(pid)
        _write_retest(pid, ["test_add_basic"])
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("passed", 0)):
            resp_repair = client.post(f"/api/projects/{pid}/repair")
        assert resp_repair.status_code == 200
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("passed", 0)):
            resp = client.post(f"/api/projects/{pid}/repair/approve")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "applied"
        assert body["application_state"] == "applied"
        assert body["final_validation"]["status"] == "passed"
        assert src_f.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"


class TestGetProjectRepair:
    def test_repair_populated_in_project_details(self, tmp_path):
        pid = _register_project(tmp_path)
        _write_meta(pid)
        _write_source(pid, "def add(a, b):\n    return a - b\n")
        _write_gt(pid)
        _write_codemap(pid)
        _write_diagnosis(pid)
        _write_retest(pid, ["test_add_basic"])
        with patch("app.execution.runner.execute_tests", return_value=_exec_result("passed", 0)):
            client.post(f"/api/projects/{pid}/repair")
        resp = client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["repair"] is not None
        assert body["repair"]["status"] == "validated_pending_approval"

    def test_repair_none_before_repair(self, tmp_path):
        pid = _register_project(tmp_path)
        resp = client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["repair"] is None
