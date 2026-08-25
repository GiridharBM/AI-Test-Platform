"""Shared pytest fixtures for Milestone 2 tests."""

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.main import app


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    """Redirect the workspace to a temp dir for every test."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setattr(config, "WORKSPACE_DIR", ws)
    return ws


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)
