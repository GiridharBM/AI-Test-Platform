"""M16-A tests: the ATP_* environment-variable configuration layer.

Covers: defaults preserved when no variables are set, overrides for every
exposed setting, validation failures on invalid values (fail loudly at import,
never silent fallback), no logging of configuration values, integration with
M15 stuck detection (the configured timeout is honored at call time), and
compatibility with the test suite's monkeypatched-workspace pattern.
"""

import importlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core import config
from app.models.pipeline import PipelineState
from app.services import pipeline as pl
from app.services import readiness

_ATP_VARS = (
    "ATP_WORKSPACE_DIR",
    "ATP_BACKEND_HOST",
    "ATP_BACKEND_PORT",
    "ATP_PIPELINE_STUCK_TIMEOUT_SECONDS",
    "ATP_TESTRUNNER_IMAGE",
)


@pytest.fixture
def env_config(request):
    """Apply ``env`` overrides and reload config; restore prior state at test end.

    The override stays live for the rest of the test (so callers can read
    module attributes after reload), and the finalizer restores the original
    environment and reloads once more, keeping tests fully isolated.
    """

    def _apply(env):
        saved = {name: os.environ.get(name) for name in _ATP_VARS}
        for name in _ATP_VARS:
            os.environ.pop(name, None)
        os.environ.update(env)

        def _restore():
            for name, old in saved.items():
                if old is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = old
            importlib.reload(config)

        request.addfinalizer(_restore)
        return importlib.reload(config)

    return _apply


def _now():
    return datetime.now(timezone.utc)


class TestDefaults:
    def test_defaults_preserved_with_no_env(self, env_config):
        mod = env_config({})
        assert mod.WORKSPACE_DIR == mod.BACKEND_DIR / "workspace"
        assert mod.BACKEND_HOST == "127.0.0.1"
        assert mod.BACKEND_PORT == 8000
        assert mod.PIPELINE_STUCK_TIMEOUT_SECONDS == 1800
        assert mod.EXECUTION_IMAGE_NAME == "ai-test-platform-testrunner"


class TestOverrides:
    def test_workspace_override(self, env_config):
        target = Path("D:\\custom\\workspace")
        assert env_config({"ATP_WORKSPACE_DIR": str(target)}).WORKSPACE_DIR == target

    def test_host_and_port_overrides(self, env_config):
        mod = env_config({"ATP_BACKEND_HOST": "0.0.0.0", "ATP_BACKEND_PORT": "9000"})
        assert mod.BACKEND_HOST == "0.0.0.0"
        assert mod.BACKEND_PORT == 9000

    def test_stuck_timeout_override(self, env_config):
        assert env_config(
            {"ATP_PIPELINE_STUCK_TIMEOUT_SECONDS": "600"}
        ).PIPELINE_STUCK_TIMEOUT_SECONDS == 600

    def test_testrunner_image_override(self, env_config):
        assert env_config(
            {"ATP_TESTRUNNER_IMAGE": "registry.example.net/runner:v2"}
        ).EXECUTION_IMAGE_NAME == "registry.example.net/runner:v2"


class TestValidation:
    @pytest.mark.parametrize("bad", ["0", "70000", "abc", "80.5", "  "])
    def test_invalid_port_rejected(self, bad, env_config):
        with pytest.raises(ValueError):
            env_config({"ATP_BACKEND_PORT": bad})

    @pytest.mark.parametrize("bad", ["0", "-5", "abc"])
    def test_invalid_timeout_rejected(self, bad, env_config):
        with pytest.raises(ValueError):
            env_config({"ATP_PIPELINE_STUCK_TIMEOUT_SECONDS": bad})

    @pytest.mark.parametrize("name", [v for v in _ATP_VARS if v != "ATP_BACKEND_PORT"])
    def test_explicitly_empty_value_is_error(self, name, env_config):
        with pytest.raises(ValueError):
            env_config({name: ""})


class TestNoLogLeak:
    def test_config_values_never_logged(self, caplog, env_config):
        secret = "SUPER-SECRET-VALUE-NEVER-LOGGED"
        with caplog.at_level("DEBUG"):
            env_config({"ATP_TESTRUNNER_IMAGE": secret})
        assert not any(secret in r.getMessage() for r in caplog.records)


class TestM15Integration:
    def test_stale_uses_configured_timeout(self, env_config):
        env_config({"ATP_PIPELINE_STUCK_TIMEOUT_SECONDS": "600"})
        state = PipelineState(
            project_id="p", pipeline_id="pipe", current_stage="profiling",
            overall_status="running", stage_started_at=_now(), updated_at=_now(),
        )
        stale_now = _now()
        recent = PipelineState.model_copy(
            state,
            update={
                "stage_started_at": stale_now - timedelta(seconds=599),
                "updated_at": stale_now - timedelta(seconds=59),
            },
        )
        abandoned = PipelineState.model_copy(
            state,
            update={
                "stage_started_at": stale_now - timedelta(seconds=601),
                "updated_at": stale_now - timedelta(seconds=601),
            },
        )
        assert pl._stale(recent, stale_now) is False
        assert pl._stale(abandoned, stale_now) is True


class TestWorkspacePatchCompat:
    def test_monkeypatched_workspace_still_honored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path)
        assert readiness.workspace_available() is True
        monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "does_not_exist")
        assert readiness.workspace_available() is False