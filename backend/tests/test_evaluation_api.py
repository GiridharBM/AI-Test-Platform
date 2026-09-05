"""Tests for the evaluation API endpoint and persistence (Milestone 10)."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.core import config
from app.models.evaluation import (
    EVAL_BLOCKED,
    EVAL_COMPLETED,
    EVAL_UNAVAILABLE,
    BenchmarkResult,
    CoverageResult,
    MutationResult,
)
from app.models.retest import ReTestResult
from app.services import project_ingestion as ingestion


def _register_project(client, tmp_path: Path) -> str:
    src = tmp_path / "myproj"
    src.mkdir()
    (src / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (src / "test_app.py").write_text("def test_add():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    resp = client.post("/api/projects/from-path", json={"path": str(src)})
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _write_generated_tests(project_id: str) -> None:
    gt = Path(config.WORKSPACE_DIR) / project_id / "generated_tests"
    gt.mkdir(parents=True, exist_ok=True)
    (gt / "test_app.py").write_text("def test_add():\n    pass\n", encoding="utf-8")


def _write_retest(project_id: str, status="fixed", diagnosis_id="d-1") -> None:
    rt = ReTestResult(
        project_id=project_id, status=status, diagnosis_id=diagnosis_id,
        created_at=datetime.now(timezone.utc),
    )
    ingestion.save_retest(config.WORKSPACE_DIR, rt.model_dump_json())


class TestEvaluateEndpoint:
    def test_project_not_found_404(self, client):
        resp = client.post("/api/projects/nonexistent/evaluate")
        assert resp.status_code == 404

    def test_post_success(self, client, tmp_path):
        pid = _register_project(client, tmp_path)
        _write_generated_tests(pid)
        _write_retest(pid)
        with patch("app.evaluation.orchestrator.coverage.run_coverage",
                   return_value=CoverageResult(status=EVAL_COMPLETED, line_percentage=80.0)), \
             patch("app.evaluation.orchestrator.mutation.run_mutation",
                   return_value=MutationResult(status=EVAL_COMPLETED, mutation_score=75.0)), \
             patch("app.evaluation.orchestrator.benchmark.run_benchmark",
                   return_value=BenchmarkResult(status=EVAL_COMPLETED, median_seconds=0.2)):
            resp = client.post(f"/api/projects/{pid}/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_version"] == 1
        assert data["status"] == EVAL_COMPLETED
        assert data["coverage"]["status"] == EVAL_COMPLETED
        assert data["mutation"]["status"] == EVAL_COMPLETED
        assert data["benchmark"]["status"] == EVAL_COMPLETED
        assert data["retest_id"] == "d-1"

    def test_post_missing_artifacts_blocked(self, client, tmp_path):
        """No generated tests => components report blocked, not a fabricated pass."""
        pid = _register_project(client, tmp_path)
        resp = client.post(f"/api/projects/{pid}/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["coverage"]["status"] == EVAL_BLOCKED
        assert data["mutation"]["status"] == EVAL_BLOCKED
        assert data["benchmark"]["status"] == EVAL_BLOCKED

    def test_post_unavailable_component(self, client, tmp_path):
        """One optional component unavailable does not fail the whole evaluation."""
        pid = _register_project(client, tmp_path)
        _write_generated_tests(pid)
        with patch("app.evaluation.orchestrator.coverage.run_coverage",
                   return_value=CoverageResult(status=EVAL_COMPLETED)), \
             patch("app.evaluation.orchestrator.mutation.run_mutation",
                   return_value=MutationResult(status=EVAL_COMPLETED)), \
             patch("app.evaluation.orchestrator.benchmark.run_benchmark",
                   return_value=BenchmarkResult(status=EVAL_UNAVAILABLE)):
            resp = client.post(f"/api/projects/{pid}/evaluate")
        assert resp.status_code == 200
        assert resp.json()["status"] == EVAL_UNAVAILABLE

    def test_post_blocked_component(self, client, tmp_path):
        pid = _register_project(client, tmp_path)
        _write_generated_tests(pid)
        with patch("app.evaluation.orchestrator.coverage.run_coverage",
                   return_value=CoverageResult(status=EVAL_BLOCKED, warnings=["blocked"])), \
             patch("app.evaluation.orchestrator.mutation.run_mutation",
                   return_value=MutationResult(status=EVAL_COMPLETED)), \
             patch("app.evaluation.orchestrator.benchmark.run_benchmark",
                   return_value=BenchmarkResult(status=EVAL_COMPLETED)):
            resp = client.post(f"/api/projects/{pid}/evaluate")
        assert resp.status_code == 200
        assert resp.json()["status"] == EVAL_BLOCKED

    def test_get_evaluation_exposed(self, client, tmp_path):
        pid = _register_project(client, tmp_path)
        _write_generated_tests(pid)
        with patch("app.evaluation.orchestrator.coverage.run_coverage",
                   return_value=CoverageResult(status=EVAL_COMPLETED)), \
             patch("app.evaluation.orchestrator.mutation.run_mutation",
                   return_value=MutationResult(status=EVAL_COMPLETED)), \
             patch("app.evaluation.orchestrator.benchmark.run_benchmark",
                   return_value=BenchmarkResult(status=EVAL_COMPLETED)):
            client.post(f"/api/projects/{pid}/evaluate")
        get_resp = client.get(f"/api/projects/{pid}")
        assert get_resp.status_code == 200
        eval_data = get_resp.json()["evaluation"]
        assert eval_data is not None
        assert eval_data["schema_version"] == 1

    def test_get_without_evaluation_returns_null(self, client, tmp_path):
        pid = _register_project(client, tmp_path)
        resp = client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["evaluation"] is None

    def test_persistence_after_api_call(self, client, tmp_path):
        pid = _register_project(client, tmp_path)
        _write_generated_tests(pid)
        with patch("app.evaluation.orchestrator.coverage.run_coverage",
                   return_value=CoverageResult(status=EVAL_COMPLETED)), \
             patch("app.evaluation.orchestrator.mutation.run_mutation",
                   return_value=MutationResult(status=EVAL_COMPLETED)), \
             patch("app.evaluation.orchestrator.benchmark.run_benchmark",
                   return_value=BenchmarkResult(status=EVAL_COMPLETED)):
            client.post(f"/api/projects/{pid}/evaluate")
        raw = ingestion.read_evaluation(config.WORKSPACE_DIR, pid)
        assert raw is not None
        assert '"project_id"' in raw


class TestEvaluationPersistence:
    def test_save_and_read(self, tmp_path):
        ws = tmp_path / "w"
        pid = "proj-eval"
        (ws / pid / ".meta").mkdir(parents=True)
        payload = ('{"project_id": "' + pid + '", "schema_version": 1, '
                   '"status": "completed", "created_at": "2021-01-01T00:00:00Z"}')
        ingestion.save_evaluation(ws, payload)
        assert (ws / pid / ".meta" / "evaluation.json").is_file()
        data = ingestion.read_evaluation(ws, pid)
        assert data is not None
        assert '"project_id"' in data

    def test_read_missing(self, tmp_path):
        assert ingestion.read_evaluation(tmp_path / "w", "nope") is None

    def test_malformed_read_returns_raw(self, tmp_path):
        ws = tmp_path / "w"
        pid = "malformed-eval"
        (ws / pid / ".meta").mkdir(parents=True)
        (ws / pid / ".meta" / "evaluation.json").write_text("{not json", encoding="utf-8")
        assert ingestion.read_evaluation(ws, pid) == "{not json"

    def test_only_writes_evaluation_json(self, tmp_path):
        ws = tmp_path / "w"
        pid = "proj-only"
        (ws / pid / ".meta").mkdir(parents=True)
        payload = ('{"project_id": "' + pid + '", "schema_version": 1, '
                   '"status": "completed", "created_at": "2021-01-01T00:00:00Z"}')
        ingestion.save_evaluation(ws, payload)
        files = [p.name for p in (ws / pid / ".meta").iterdir()]
        assert files == ["evaluation.json"]


class TestExistingAPIRegression:
    """Verify existing M1-M9 endpoints still work after M10 changes."""

    def test_from_path_still_works(self, client, tmp_path):
        d = tmp_path / "p"
        d.mkdir()
        resp = client.post("/api/projects/from-path", json={"path": str(d)})
        assert resp.status_code == 200

    def test_get_returns_all_fields(self, client, tmp_path):
        pid = _register_project(client, tmp_path)
        resp = client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        for field in ("profile", "codemap", "test_plan", "test_generation",
                      "execution", "diagnosis", "improvement", "retest", "evaluation"):
            assert field in data
