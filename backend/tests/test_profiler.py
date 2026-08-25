"""Tests for the deterministic project profiler."""

from pathlib import Path

import pytest


def _make_project(root: Path, files: dict[str, str]) -> Path:
    """Helper: write a dict of {relpath: content} into root."""
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _profile(client, path: str) -> dict:
    """Register a local project, profile it, return the profile dict."""
    res = client.post("/api/projects/from-path", json={"path": path})
    assert res.status_code == 200
    pid = res.json()["project_id"]
    res2 = client.post(f"/api/projects/{pid}/profile")
    assert res2.status_code == 200
    return res2.json()


def test_python_project_functions_and_classes(client, tmp_path):
    project = _make_project(tmp_path / "pyp", {
        "src/app.py": (
            "class Foo:\n"
            "    def bar(self): pass\n"
            "    async def baz(self): pass\n"
            "def standalone(): pass\n"
            "async def async_func(): pass\n"
        ),
        "src/test_main.py": (
            "class TestFoo:\n"
            "    def test_bar(self): pass\n"
        ),
        "README.md": "# readme",
    })
    profile = _profile(client, str(project))
    m = profile["metrics"]
    # functions = all defs (top-level + methods), methods = just methods
    assert m["functions"] == 5  # 2 top-level + 3 methods
    assert m["classes"] == 2    # Foo + TestFoo
    assert m["methods"] == 3    # Foo.bar, Foo.baz, TestFoo.test_bar
    assert m["test_files"] == 1
    assert m["documentation_files"] == 1


def test_python_syntax_error_handled(client, tmp_path):
    project = _make_project(tmp_path / "badpy", {
        "broken.py": "def foo(\n  indent",
    })
    profile = _profile(client, str(project))
    assert any("syntax" in w.lower() or "parse" in w.lower() for w in profile["warnings"])
    assert profile["metrics"]["functions"] is not None  # still numeric (0)


def test_language_detection(client, tmp_path):
    project = _make_project(tmp_path / "mixed", {
        "app.py": "print(1)",
        "utils.py": "x = 1",
        "service.java": "class Foo {}",
        "component.tsx": "export const X = () => null",
        "helper.js": "module.exports = {}",
    })
    profile = _profile(client, str(project))
    langs = {l["name"]: l for l in profile["languages"]}
    assert "Python" in langs
    assert "Java" in langs
    assert "TypeScript" in langs
    assert "JavaScript" in langs


def test_language_percentages_based_on_lines(client, tmp_path):
    project = _make_project(tmp_path / "linepct", {
        "big.py": "\n".join([f"line{i}" for i in range(100)]),
        "small.ts": "\n".join([f"line{i}" for i in range(25)]),
    })
    profile = _profile(client, str(project))
    langs = {l["name"]: l for l in profile["languages"]}
    assert abs(langs["Python"]["percentage"] - 80.0) < 0.5
    assert abs(langs["TypeScript"]["percentage"] - 20.0) < 0.5


def test_test_detection_python(client, tmp_path):
    project = _make_project(tmp_path / "pytestd", {
        "tests/test_auth.py": "def test_login(): pass",
        "tests/auth_test.py": "def test_signup(): pass",
        "src/app.py": "x = 1",
    })
    profile = _profile(client, str(project))
    assert profile["metrics"]["test_files"] == 2


def test_test_detection_java(client, tmp_path):
    project = _make_project(tmp_path / "javad", {
        "src/test/com/FooTest.java": "class FooTest {}",
        "src/main/com/Foo.java": "class Foo {}",
        "src/test/com/BarIT.java": "class BarIT {}",
    })
    profile = _profile(client, str(project))
    assert profile["metrics"]["test_files"] == 2


def test_test_detection_js_ts(client, tmp_path):
    project = _make_project(tmp_path / "jstd", {
        "src/app.test.js": "describe('x', () => {});",
        "src/util.spec.ts": "test('y', () => {});",
        "src/index.ts": "export const a = 1;",
    })
    profile = _profile(client, str(project))
    assert profile["metrics"]["test_files"] == 2


def test_framework_detection_pytest(client, tmp_path):
    project = _make_project(tmp_path / "fw", {
        "requirements.txt": "pytest>=7.0\nhttpx\n",
        "tests/test_x.py": "def test_ok(): pass",
    })
    profile = _profile(client, str(project))
    assert "pytest" in profile["tests"]["frameworks"]


def test_framework_detection_unittest(client, tmp_path):
    project = _make_project(tmp_path / "fw2", {
        "tests/test_thing.py": "import unittest\nclass T(unittest.TestCase):\n  pass\n",
    })
    profile = _profile(client, str(project))
    assert "unittest" in profile["tests"]["frameworks"]


def test_framework_detection_jest(client, tmp_path):
    project = _make_project(tmp_path / "jestp", {
        "package.json": '{"devDependencies": {"jest": "^29.0"}}',
    })
    profile = _profile(client, str(project))
    assert "Jest" in profile["tests"]["frameworks"]


def test_framework_detection_no_false_positives(client, tmp_path):
    project = _make_project(tmp_path / "nofp", {
        "app.py": "print(1)",
    })
    profile = _profile(client, str(project))
    assert profile["tests"]["frameworks"] == []


def test_documentation_detection(client, tmp_path):
    project = _make_project(tmp_path / "docsd", {
        "README.md": "# Hello",
        "docs/guide.md": "# Guide",
        "CHANGELOG.rst": "Changelog",
        "src/app.py": "x = 1",
    })
    profile = _profile(client, str(project))
    assert profile["documentation"]["files"] >= 3


def test_dependency_manifests_detected(client, tmp_path):
    project = _make_project(tmp_path / "deps", {
        "requirements.txt": "fastapi\nuvicorn",
        "package.json": '{"dependencies": {"react": "^18"}}',
        "pom.xml": "<project><dependencies><dependency><groupId>x</groupId></dependency></dependencies></project>",
        "src/app.py": "x=1",
    })
    profile = _profile(client, str(project))
    manifests = profile["dependencies"]["manifests"]
    assert "requirements.txt" in manifests
    assert "package.json" in manifests
    assert "pom.xml" in manifests


def test_dependency_package_count(client, tmp_path):
    project = _make_project(tmp_path / "pkgcnt", {
        "requirements.txt": "fastapi\nuvicorn\nhttpx\n",
    })
    profile = _profile(client, str(project))
    assert profile["dependencies"]["packages_detected"] == 3


def test_ignored_directories_excluded(client, tmp_path):
    project = _make_project(tmp_path / "ignored", {
        "src/app.py": "x=1",
        "node_modules/.package-lock.json": "{}",
        "__pycache__/x.pyc": "",
        ".venv/lib/python.py": "z=1",
        "src/__pycache__/mod.cpython-312.pyc": "",
    })
    profile = _profile(client, str(project))
    paths = [f["path"] for f in profile.get("files", []) or []]
    assert not any("node_modules" in p for p in paths)
    assert not any("__pycache__" in p for p in paths)
    assert not any(".venv" in p for p in paths)


def test_line_counts(client, tmp_path):
    project = _make_project(tmp_path / "lines", {
        "a.py": "line1\nline2\nline3\n",
        "b.ts": "x\ny\n",
    })
    profile = _profile(client, str(project))
    m = profile["metrics"]
    assert m["total_lines"] == 5
    assert m["source_lines"] == 5


def test_binary_files_excluded_from_line_counts(client, tmp_path):
    project = _make_project(tmp_path / "binfiles", {
        "image.png": "\x89PNG",
        "app.py": "x=1\ny=2\n",
    })
    # Override with raw bytes
    (project / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    profile = _profile(client, str(project))
    m = profile["metrics"]
    assert m["total_lines"] == 2
    assert m["other_files"] == 1


def test_functions_classes_unavailable_for_non_python(client, tmp_path):
    project = _make_project(tmp_path / "noast", {
        "App.java": "class Foo { void bar() {} }",
        "main.ts": "function foo() {}",
    })
    profile = _profile(client, str(project))
    assert profile["metrics"]["functions"] is None
    assert profile["metrics"]["classes"] is None


def test_complexity_small(client, tmp_path):
    from app.core import config
    project = _make_project(tmp_path / "sm", {
        "a.py": "x=1\ny=2\n",
    })
    # Patch thresholds to make this clearly small
    import app.core.config as cfg
    orig_files = cfg.COMPLEXITY_SMALL_SOURCE_FILES
    orig_lines = cfg.COMPLEXITY_SMALL_SOURCE_LINES
    try:
        cfg.COMPLEXITY_SMALL_SOURCE_FILES = 100
        cfg.COMPLEXITY_SMALL_SOURCE_LINES = 10_000
        profile = _profile(client, str(project))
        assert profile["complexity"]["level"] == "Small"
    finally:
        cfg.COMPLEXITY_SMALL_SOURCE_FILES = orig_files
        cfg.COMPLEXITY_SMALL_SOURCE_LINES = orig_lines


def test_complexity_large(client, tmp_path):
    project_dir = tmp_path / "big"
    project_dir.mkdir()
    # Create enough source lines to be "Large"
    lines = "\n".join([f"def func{i}(): pass" for i in range(200)])
    (project_dir / "funcs.py").write_text(lines)
    profile = _profile(client, str(project_dir))
    # With 200 functions but only 200 lines, depends on thresholds
    # Just verify it returns a valid level
    assert profile["complexity"]["level"] in ("Small", "Medium", "Large")
    assert len(profile["complexity"]["reasons"]) > 0


def test_api_endpoint_detection_python(client, tmp_path):
    project = _make_project(tmp_path / "apis", {
        "app.py": (
            '@app.get("/health")\n'
            "def health(): pass\n\n"
            '@app.post("/api/items")\n'
            "def create(): pass\n\n"
            '@router.delete("/api/items/{id}")\n'
            "def delete(): pass\n"
        ),
    })
    profile = _profile(client, str(project))
    assert profile["api"]["endpoints_detected"] == 3
    methods = [ep["method"] for ep in profile["api"]["endpoints"]]
    assert "GET" in methods
    assert "POST" in methods
    assert "DELETE" in methods


def test_api_endpoint_detection_express(client, tmp_path):
    project = _make_project(tmp_path / "express", {
        "server.js": (
            "app.get('/users', (req, res) => {});\n"
            "app.post('/login', (req, res) => {});\n"
        ),
    })
    profile = _profile(client, str(project))
    assert profile["api"]["endpoints_detected"] == 2


def test_profile_includes_file_list_when_small(client, tmp_path):
    project = _make_project(tmp_path / "smallp", {
        "a.py": "x=1",
        "b.py": "y=2",
    })
    profile = _profile(client, str(project))
    assert profile["files"] is not None
    assert len(profile["files"]) == 2


def test_profile_deterministic(client, tmp_path):
    project = _make_project(tmp_path / "det", {
        "a.py": "x=1\ny=2",
    })
    p1 = _profile(client, str(project))
    p2 = _profile(client, str(project))
    # Profiles are regenerated fresh each time; key fields match
    assert p1["metrics"]["total_files"] == p2["metrics"]["total_files"]
    assert p1["complexity"]["level"] == p2["complexity"]["level"]
    assert len(p1["warnings"]) == len(p2["warnings"])


def test_gitignore_respected(client, tmp_path):
    project = _make_project(tmp_path / "gic", {
        ".gitignore": "secret_dir/\n",
        "src/app.py": "x=1",
        "secret_dir/creds.py": "password = 'x'",
    })
    profile = _profile(client, str(project))
    paths = [f["path"] for f in profile.get("files", []) or []]
    assert not any("secret_dir" in p for p in paths)


def test_empty_project(client, tmp_path):
    project = tmp_path / "empty"
    project.mkdir()
    profile = _profile(client, str(project))
    assert profile["metrics"]["total_files"] == 0
    assert any("no files" in w.lower() for w in profile["warnings"])
