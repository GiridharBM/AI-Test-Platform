"""Tests for the re-test API endpoint and persistence (Milestone 9)."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core import config
from app.main import app
from app.models.execution import ExecutionSummary, TestExecutionResult, TestFileResult
from app.models.improvement import ImprovementChange, ImprovementResult
from app.services import project_ingestion as ingestion

client = TestClient(app, raise_server_exceptions=False)


def _register_project(tmp_path: Path) -> str:
    src = tmp_path / "myproject"
    src.mkdir()
    (src / "app.py").write_text('def add(a, b):\n    return a + b\n', encoding="utf-8")
    (src / "test_app.py").write_text(
        'def test_add():\n    assert 1 + 1 == 2\n', encoding="utf-8")
    resp = client.post("/api/projects/from-path", json={"path": str(src)})
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _run_pipeline(project_id: str) -> None:
    for step in ("profile", "discover", "plan", "generate"):
        resp = client.post(f"/api/projects/{project_id}/{step}")
        assert resp.status_code == 200


def _write_execution(project_id: str, file_results=None):
    exec_result = TestExecutionResult(
        project_id=project_id,
        overall_status="failed",
        exit_code=1,
        summary=ExecutionSummary(total_files=1, passed=0, failed=1),
        file_results=file_results or [
            TestFileResult(file_path="test_app.py", status="failed"),
        ],
    )
    ingestion.save_execution(config.WORKSPACE_DIR, exec_result.model_dump_json())


def _write_improvement(project_id: str, status="improved", changes=None):
    imp = ImprovementResult(
        project_id=project_id,
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        status=status,
        diagnosis_id="diag123",
        changes=changes or [
            ImprovementChange(
                finding_id="f1",
                test_file="test_app.py",
                test_function="test_add",
                status="improved",
            ),
        ],
        files_modified=1 if status == "improved" else 0,
    )
    ingestion.save_improvement(config.WORKSPACE_DIR, imp.model_dump_json())


def _diagnose(project_id: str):
    resp = client.post(f"/api/projects/{project_id}/diagnose")
    assert resp.status_code == 200
    return resp.json()


class TestRetestEndpoint:
    def test_project_not_found_returns_404(self):
        resp = client.post("/api/projects/nonexistent/retest")
        assert resp.status_code == 404

    def test_no_improvement_returns_422(self, tmp_path):
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)
        resp = client.post(f"/api/projects/{project_id}/retest")
        assert resp.status_code == 422
        assert "improve" in resp.json()["detail"].lower()

    def test_retest_succeeds_after_improve(self, tmp_path):
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)
        _write_execution(project_id)
        _diagnose(project_id)
        _write_improvement(project_id)

        resp = client.post(f"/api/projects/{project_id}/retest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_version"] == 1
        assert "status" in data
        assert data["status"] in ("fixed", "still_failing", "regression",
                                  "passed", "blocked", "unavailable", "no_op")

    def test_retest_persisted_and_returned_by_get(self, tmp_path):
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)
        _write_execution(project_id)
        _diagnose(project_id)
        _write_improvement(project_id)

        client.post(f"/api/projects/{project_id}/retest")

        get_resp = client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        retest = get_resp.json()["retest"]
        assert retest is not None
        assert retest["schema_version"] == 1

    def test_get_without_retest_returns_null(self, tmp_path):
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)
        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["retest"] is None

    def test_retest_no_op_when_improvement_no_change(self, tmp_path):
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)
        _write_improvement(project_id, status="no_change", changes=[])

        resp = client.post(f"/api/projects/{project_id}/retest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_op"
        assert len(data["selected_tests"]) == 0

    def test_retest_blocked_when_improvement_blocked(self, tmp_path):
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)
        _write_improvement(project_id, status="blocked", changes=[])

        resp = client.post(f"/api/projects/{project_id}/retest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_op"


class TestRetestPersistence:
    def test_save_and_read(self, tmp_path):
        ws = tmp_path / "workspace"
        pid = "proj-retest"
        (ws / pid / ".meta").mkdir(parents=True)
        from datetime import datetime, timezone
        payload = (
            '{"project_id": "' + pid + '", "schema_version": 1, '
            '"status": "no_op", "created_at": "2021-01-01T00:00:00Z"}'
        )
        ingestion.save_retest(ws, payload)
        assert (ws / pid / ".meta" / "retest.json").is_file()
        data = ingestion.read_retest(ws, pid)
        assert data is not None
        assert '"project_id"' in data

    def test_read_missing(self, tmp_path):
        ws = tmp_path / "workspace"
        assert ingestion.read_retest(ws, "nonexistent") is None

    def test_malformed_read_returns_raw(self, tmp_path):
        ws = tmp_path / "workspace"
        pid = "malformed-retest"
        (ws / pid / ".meta").mkdir(parents=True)
        (ws / pid / ".meta" / "retest.json").write_text("{not json", encoding="utf-8")
        assert ingestion.read_retest(ws, pid) == "{not json"


class TestExistingAPIRegression:
    """Verify existing M1-M8 endpoints still work after M9 changes."""

    def test_upload_still_works(self):
        resp = client.post("/api/projects/upload", files={"files": ("f.txt", b"hi")})
        # May fail validation but shouldn't 500 from import errors
        assert resp.status_code in (200, 400, 422)

    def test_from_path_still_works(self, tmp_path):
        d = tmp_path / "proj"
        d.mkdir()
        resp = client.post("/api/projects/from-path", json={"path": str(d)})
        assert resp.status_code == 200

    def test_improve_endpoint_exists(self, tmp_path):
        pid = _register_project(tmp_path)
        _run_pipeline(pid)
        resp = client.post(f"/api/projects/{pid}/improve")
        # Should work (improve returns 200 or 422 depending on prior stages)
        assert resp.status_code in (200, 422)

    def test_get_returns_all_fields(self, tmp_path):
        pid = _register_project(tmp_path)
        _run_pipeline(pid)
        resp = client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "codemap" in data
        assert "test_plan" in data
        assert "test_generation" in data
        assert "execution" in data
        assert "diagnosis" in data
        assert "improvement" in data
        assert "retest" in data
