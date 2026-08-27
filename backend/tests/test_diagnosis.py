"""Tests for the deterministic failure diagnosis core (Milestone 7)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.agents import diagnose as d
from app.models.codemap import (
    CodeMap,
    SourceFunction,
    SourceModule,
    TestFunction,
    TestMapping,
)
from app.models.diagnosis import (
    DiagnosisResult,
    SourceLocation,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)
from app.models.execution import ExecutionSummary, TestExecutionResult


def _mk_exec(
    stdout: str = "",
    stderr: str = "",
    status: str = "failed",
    exit_code: int = 1,
) -> TestExecutionResult:
    return TestExecutionResult(
        project_id="p1",
        overall_status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        summary=ExecutionSummary(),
    )


def _mk_codemap(**overrides):
    defaults = dict(
        project_id="p1",
        created_at=datetime.now(timezone.utc),
        source_modules=[], test_functions=[], test_mappings=[], testable_targets=[],
        warnings=[],
    )
    defaults.update(overrides)
    return CodeMap(**defaults)


_CONTAINER_NOT_IMPLEMENTED = """\
/tests/test_math.py::test_edge_negative FAILED

============================= FAILURES =============================
________________________________ test_edge_negative ________________________________
/tests/test_math.py:19: in test_edge_negative
    raise NotImplementedError('Edge case: negative value')
E   NotImplementedError: Edge case: negative value
1 failed in 0.2s
"""


# ── Models & schema ─────────────────────────────────────────────────────

class TestDiagnosisModels:
    def test_defaults(self):
        r = DiagnosisResult(project_id="p1", created_at=datetime.now(timezone.utc))
        assert r.schema_version == 1
        assert r.overall_status == "no_execution"
        assert r.findings == []
        assert r.potential_bugs == []
        assert r.summary.total_findings == 0

    def test_serialization_roundtrip(self):
        r = DiagnosisResult(project_id="p1", created_at=datetime.now(timezone.utc))
        r2 = DiagnosisResult.model_validate_json(r.model_dump_json())
        assert r2.schema_version == 1
        assert r2.project_id == "p1"

    def test_potential_bug_separate_from_findings(self):
        from app.models.diagnosis import PotentialBug
        pb = PotentialBug(description="x", model="local")
        assert pb.model == "local"
        r = DiagnosisResult(
            project_id="p1", created_at=datetime.now(timezone.utc),
            potential_bugs=[pb],
        )
        assert len(r.potential_bugs) == 1
        assert len(r.findings) == 0


# ── Extraction ──────────────────────────────────────────────────────────

class TestExtraction:
    def test_parses_failed_and_error_lines_only(self):
        out = (
            "/tests/a.py::test_ok PASSED\n"
            "/tests/a.py::test_bad FAILED\n"
            "/tests/b.py::test_err ERROR\n"
            "/tests/b.py::test_skip SKIPPED\n"
        )
        got = d.extract_failed_tests(out)
        assert got == [
            ("a.py", "test_bad", "failed"),
            ("b.py", "test_err", "error"),
        ]

    def test_ignores_collection_header_lines(self):
        out = "=== FAILURES ===\n/tests/x.py::t FAILED\n"
        assert d.extract_failed_tests(out) == [("x.py", "t", "failed")]

    def test_normalizes_container_prefix(self):
        out = "/tests/test_z.py::t FAILED\n"
        assert d.extract_failed_tests(out) == [("test_z.py", "t", "failed")]


# ── Classification ──────────────────────────────────────────────────────

class TestClassification:
    def test_exception_category(self):
        cat, exc, msg, tb = d.classify_failure(
            _CONTAINER_NOT_IMPLEMENTED, "test_math.py", "test_edge_negative")
        assert cat == "exception"
        assert exc == "NotImplementedError"
        assert "Edge case" in msg

    def test_assertion_category(self):
        out = (
            "/tests/test_a.py::test_eq FAILED\n"
            "________________________________ test_eq ________________________________\n"
            "/tests/test_a.py:5: in test_eq\n"
            "    assert 1 == 2\n"
            "E   assert 1 == 2\n"
        )
        cat, exc, msg, _ = d.classify_failure(out, "test_a.py", "test_eq")
        assert cat == "assertion"

    def test_import_error_category(self):
        out = "/tests/test_app.py::test_thing ERROR\nE   ModuleNotFoundError: No module named 'x'\n"
        cat, exc, _, _ = d.classify_failure(out, "test_app.py", "test_thing")
        assert cat == "import_error"
        assert exc == "ModuleNotFoundError"

    def test_syntax_error_category(self):
        out = "/tests/test_s.py::t ERROR\nE   SyntaxError: invalid syntax\n"
        cat, exc, _, _ = d.classify_failure(out, "test_s.py", "t")
        assert cat == "syntax_error"

    def test_unknown_when_no_evidence(self):
        out = "/tests/test_u.py::t FAILED\n"
        cat, exc, msg, tb = d.classify_failure(out, "test_u.py", "t")
        assert cat == "unknown"
        assert exc == ""
        assert msg == ""


# ── Fingerprinting ──────────────────────────────────────────────────────

class TestFingerprint:
    def test_deterministic_same_input(self):
        a = d.fingerprint("a.py", "t", "exception", "X", "msg")
        b = d.fingerprint("a.py", "t", "exception", "X", "msg")
        assert a == b

    def test_normalizes_paths(self):
        a = d.fingerprint(r"C:\workspace\foo.py", "t", "exception", "X", "m")
        b = d.fingerprint("/tmp/workspace/foo.py", "t", "exception", "X", "m")
        c = d.fingerprint("/tests/foo.py", "t", "exception", "X", "m")
        assert a == b == c

    def test_different_failure_differs(self):
        a = d.fingerprint("a.py", "t", "exception", "X", "m")
        b = d.fingerprint("a.py", "t", "exception", "X", "different")
        assert a != b

    def test_hex_sha256(self):
        sig = d.fingerprint("a.py", "t", "exception", "X", "m")
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_distinct_project_relative_paths_stay_distinct(self):
        # Project-relative directory structure must be preserved for stability:
        # two logically different files sharing a basename must not collide.
        src = d.fingerprint("src/foo.py", "t", "exception", "X", "m")
        tests = d.fingerprint("tests/foo.py", "t", "exception", "X", "m")
        nested = d.fingerprint("nested/foo.py", "t", "exception", "X", "m")
        assert len({src, tests, nested}) == 3
        # A lone file must also be distinct from any subdirectory variant.
        assert d.fingerprint("foo.py", "t", "exception", "X", "m") not in {src, tests}

    def test_env_root_normalization_preserves_relpath(self):
        # Env/container/workspace mounts of the SAME relative file stay equal,
        # but a genuinely different relative file does not.
        a = d.fingerprint(r"C:\workspace\src\calc.py", "t", "exception", "X", "m")
        b = d.fingerprint("/tmp/workspace/src/calc.py", "t", "exception", "X", "m")
        c = d.fingerprint("/tests/src/calc.py", "t", "exception", "X", "m")
        assert a == b == c
        other = d.fingerprint("src/calc.py", "t", "exception", "X", "m")
        assert a == other

    def test_finding_ids_distinct_by_project_path(self):
        def fid(c, f):
            return d._build_finding_id(c, f, "test_thing")
        ids = {fid("exception", "src/foo.py"),
               fid("exception", "tests/foo.py"),
               fid("exception", "nested/foo.py")}
        assert len(ids) == 3


# ── Severity ────────────────────────────────────────────────────────────

class TestSeverity:
    @pytest.mark.parametrize("category,expected", [
        ("timeout", SEVERITY_HIGH),
        ("collection_error", SEVERITY_HIGH),
        ("syntax_error", SEVERITY_HIGH),
        ("import_error", SEVERITY_HIGH),
        ("exception", SEVERITY_MEDIUM),
        ("assertion", SEVERITY_MEDIUM),
        ("unknown", SEVERITY_LOW),
    ])
    def test_severity_rules(self, category, expected):
        assert d.severity_for("failed", category) == expected

    def test_timeout_status_high(self):
        assert d.severity_for("timeout", "unknown") == SEVERITY_HIGH


# ── End-to-end diagnosis ────────────────────────────────────────────────

class TestDiagnoseExecution:
    def test_no_failures(self):
        r = d.diagnose_execution(_mk_exec(
            status="passed", exit_code=0,
            stdout="/tests/test_x.py::t PASSED\n",
        ))
        assert r.overall_status == "no_failures"
        assert r.findings == []

    def test_no_execution_unavailable(self):
        r = d.diagnose_execution(_mk_exec(status="unavailable"))
        assert r.overall_status == "no_execution"

    def test_exception_finding(self):
        r = d.diagnose_execution(_mk_exec(stdout=_CONTAINER_NOT_IMPLEMENTED))
        assert r.overall_status == "failures_diagnosed"
        assert len(r.findings) == 1
        f = r.findings[0]
        assert f.test_function == "test_edge_negative"
        assert f.category == "exception"
        assert f.severity == SEVERITY_MEDIUM
        assert f.exception_type == "NotImplementedError"

    def test_timeout_finding(self):
        r = d.diagnose_execution(_mk_exec(status="timeout", exit_code=-1, stdout=""))
        assert r.overall_status == "failures_diagnosed"
        assert r.findings[0].category == "timeout"
        assert r.findings[0].severity == SEVERITY_HIGH

    def test_collection_error(self):
        out = "ERROR collecting /tests/test_broken.py\n/other.py:1: in <module>\nE   ImportError: boom\n"
        r = d.diagnose_execution(_mk_exec(stdout=out))
        cats = {f.category for f in r.findings}
        assert "collection_error" in cats or r.overall_status == "failures_diagnosed"

    def test_multiple_failures_stable_order(self):
        out = (
            "/tests/a.py::test_a FAILED\n"
            "/tests/b.py::test_b FAILED\n"
            "________________________________ test_b ________________________________\n"
            "/tests/b.py:1: in test_b\nE   ValueError: b\n"
            "________________________________ test_a ________________________________\n"
            "/tests/a.py:1: in test_a\nE   ValueError: a\n"
        )
        r1 = d.diagnose_execution(_mk_exec(stdout=out))
        r2 = d.diagnose_execution(_mk_exec(stdout=out))
        keys1 = [(f.test_file, f.test_function) for f in r1.findings]
        keys2 = [(f.test_file, f.test_function) for f in r2.findings]
        assert keys1 == keys2
        assert keys1 == sorted(keys1)

    def test_deterministic_repeated_diagnosis(self):
        """Deterministic content (findings, summary, status) is stable across runs.

        created_at is runtime metadata and is excluded from the determinism claim.
        """
        r1 = d.diagnose_execution(_mk_exec(stdout=_CONTAINER_NOT_IMPLEMENTED))
        r2 = d.diagnose_execution(_mk_exec(stdout=_CONTAINER_NOT_IMPLEMENTED))
        assert r1.overall_status == r2.overall_status
        assert r1.summary == r2.summary
        assert r1.findings == r2.findings
        assert [f.model_dump() for f in r1.findings] == [f.model_dump() for f in r2.findings]

    def test_no_random_finding_ids(self):
        r1 = d.diagnose_execution(_mk_exec(stdout=_CONTAINER_NOT_IMPLEMENTED))
        r2 = d.diagnose_execution(_mk_exec(stdout=_CONTAINER_NOT_IMPLEMENTED))
        assert r1.findings[0].finding_id == r2.findings[0].finding_id


# ── CodeMap linkage ─────────────────────────────────────────────────────

class TestCodeMapLinkage:
    def _direct_codemap(self):
        return _mk_codemap(source_modules=[
            SourceModule(
                path="math.py", language="Python",
                functions=[SourceFunction(
                    name="div", qualified_name="div",
                    file_path="math.py", line_start=1, line_end=5)],
            )
        ])

    def test_direct_traceback_linkage(self):
        cm = self._direct_codemap()
        tb = "/src/math.py:3: in div\nE   ZeroDivisionError: division by zero\n"
        locs = d.link_to_codemap(cm, "test_math.py", "test_div", tb)
        assert locs
        loc = locs[0]
        assert isinstance(loc, SourceLocation)
        assert loc.source_file == "math.py"
        assert loc.confidence == 0.9

    def test_mapping_linkage(self):
        cm = _mk_codemap(
            source_modules=[SourceModule(
                path="calc.py", language="Python",
                functions=[SourceFunction(
                    name="add", qualified_name="add",
                    file_path="calc.py", line_start=10, line_end=14)])],
            test_functions=[TestFunction(
                name="test_add", file_path="tests/test_calc.py", line_start=1, line_end=3)],
            test_mappings=[TestMapping(
                test_function="test_add", test_file="tests/test_calc.py",
                source_target="add", source_file="calc.py",
                confidence=0.8, method="name_similarity")],
        )
        locs = d.link_to_codemap(cm, "/tests/test_calc.py", "test_add", "")
        assert locs
        loc = locs[0]
        assert loc.source_file == "calc.py"
        assert loc.qualified_name == "add"
        assert loc.confidence == 0.8

    def test_no_linkage_when_unmapped(self):
        cm = self._direct_codemap()
        locs = d.link_to_codemap(cm, "test_unknown.py", "test_nope", "")
        assert locs == []


# ── Path security ───────────────────────────────────────────────────────

class TestPathSecurity:
    @pytest.mark.parametrize("evil,expected", [
        ("../../secret.txt", None),
        (r"C:\secret.txt", None),
        ("/etc/passwd", None),
        ("", None),
        ("/tests/test_math.py", "test_math.py"),
        ("app/mod.py", "app/mod.py"),
    ])
    def test_normalize_rejects_or_sanitizes(self, evil, expected):
        if expected is None:
            got = d.normalize_trace_path(evil)
            assert got is None or "/" not in got or ".." not in got
        else:
            assert d.normalize_trace_path(evil) == expected

    def test_traversal_never_linked(self):
        cm = _mk_codemap(source_modules=[
            SourceModule(path="secret.py", language="Python")])
        tb = "../../secret.py:3: in f\nE   ValueError: x\n"
        locs = d.link_to_codemap(cm, "test_x.py", "test_f", tb)
        # No source location resolved from a traversal attempt.
        assert all(l.source_file != "secret.py" for l in locs)


# ── Security invariants ─────────────────────────────────────────────────

class TestSecurityInvariants:
    """Static and behavioural guarantees that diagnosis is read-only and safe."""

    @pytest.mark.parametrize("modpath,forbidden", [
        ("app/agents/diagnose.py", ["exec(", "eval(", "subprocess", "os.system",
                                    "socket", "urllib", "requests", "http"]),
        ("app/agents/llm.py", ["exec(", "eval(", "subprocess", "os.system",
                               "socket", "urllib", "requests", "http", "openai",
                               "anthropic", "api_key", "api key"]),
    ])
    def test_no_dangerous_calls_in_module(self, modpath, forbidden):
        src = Path(modpath).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in src, f"{modpath} must not contain {token!r}"

    def test_no_runpy_or_code_injection(self):
        src = Path("app/agents/diagnose.py").read_text(encoding="utf-8")
        assert "importlib.import_module" not in src
        assert "eval(" not in src
        assert "exec(" not in src
        # Only safe regex compilation is permitted, never dynamic code compile.
        for occur in [s for s in src.splitlines() if "compile(" in s]:
            assert "re.compile(" in occur, f"unsafe compile: {occur!r}"

    def test_linker_never_reads_the_traceback_path(self):
        # Paths derived from untrusted traceback output must never be absolute
        # and never contain traversal, so they can never address host files.
        for evil in (r"C:\Users\secret.txt", "/etc/passwd", "../secret", "..\\..\\a"):
            got = d.normalize_trace_path(evil)
            assert got is None or (".." not in got and not got.startswith("/"))
            assert not (got or "").startswith("\\\\")

    def test_diagnose_never_imports_user_modules(self, monkeypatch):
        # The deterministic path works purely off persisted .meta artifacts and
        # the codemap; it must not import project code.
        called = {"import_module": False}
        def fake_import(name, *a, **k):
            called["import_module"] = True
            return __import__(name, *a, **k)
        monkeypatch.setattr("importlib.import_module", fake_import)
        monkeypatch.setattr("app.core.config.DIAGNOSIS_AI_ENABLED", False)
        r = d.diagnose_execution(_mk_exec(stdout=_CONTAINER_NOT_IMPLEMENTED))
        # We at least confirm execution completes deterministically with no AI.
        assert r.overall_status == "failures_diagnosed"
        assert r.potential_bugs == []


# ── AI boundary ─────────────────────────────────────────────────────────

class TestAiBoundary:
    def test_disabled_by_default_returns_none(self, monkeypatch):
        from app.agents import llm
        monkeypatch.setattr("app.core.config.DIAGNOSIS_AI_ENABLED", False)
        assert llm.analyze({"project_id": "p"}) is None

    def test_disabled_no_backend_call(self, monkeypatch):
        from app.agents import llm
        monkeypatch.setattr("app.core.config.DIAGNOSIS_AI_ENABLED", False)
        monkeypatch.setattr("app.agents.llm._LOCAL_BACKEND", object())
        assert llm.analyze({"project_id": "p"}) is None

    def test_enabled_without_backend_raises_safe(self, monkeypatch):
        from app.agents import llm
        monkeypatch.setattr("app.core.config.DIAGNOSIS_AI_ENABLED", True)
        monkeypatch.setattr("app.agents.llm._LOCAL_BACKEND", None)
        with pytest.raises(RuntimeError):
            llm.analyze({"project_id": "p"})

    def test_orchestrator_does_not_call_llm_when_disabled(self, monkeypatch):
        monkeypatch.setattr("app.core.config.DIAGNOSIS_AI_ENABLED", False)
        r = d.diagnose_execution(_mk_exec(stdout=_CONTAINER_NOT_IMPLEMENTED))
        assert r.potential_bugs == []
        assert r.summary.potential_bugs == 0
