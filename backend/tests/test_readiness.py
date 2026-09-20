"""O2 readiness endpoint tests (GET /ready).

Covers ready / not-ready decisions for each documented prerequisite,
the deterministic response shape, and the unchanged /health contract.
The docker probe is monkeypatched so tests never touch a real daemon.
"""

from app.core import config
from app.execution import runner


def test_ready_when_all_prerequisites_available(client, monkeypatch):
    monkeypatch.setattr(runner, "_docker_probe", lambda: (True, ""))
    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json() == {
        "status": "ready",
        "checks": {"workspace": True, "runtime": True},
    }


def test_not_ready_when_workspace_unavailable(client, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_docker_probe", lambda: (True, ""))
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "WORKSPACE_DIR", blocker / "workspace")
    res = client.get("/ready")
    assert res.status_code == 503
    assert res.json()["status"] == "not_ready"
    assert res.json()["checks"] == {"workspace": False, "runtime": True}


def test_not_ready_when_runtime_unavailable(client, monkeypatch):
    monkeypatch.setattr(runner, "_docker_probe", lambda: (False, "daemon down"))
    res = client.get("/ready")
    assert res.status_code == 503
    assert res.json() == {
        "status": "not_ready",
        "checks": {"workspace": True, "runtime": False},
    }


def test_ready_response_never_leaks_paths_or_probe_detail(client, monkeypatch):
    monkeypatch.setattr(runner, "_docker_probe", (lambda: (False, "/secret/path")))
    res = client.get("/ready")
    body = res.json()
    assert set(body) == {"status", "checks"}
    assert set(body["checks"]) == {"workspace", "runtime"}
    assert "/secret/path" not in str(body)


def test_health_contract_unchanged(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "ai-test-platform"}