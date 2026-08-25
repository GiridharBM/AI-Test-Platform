"""Tests for the deterministic test scaffold generator."""

import ast
from datetime import datetime, timezone

from app.models.codemap import (
    CodeMap,
    CoverageSummary,
    SourceClass,
    SourceFunction,
    SourceModule,
    TestMapping,
    TestableTarget,
)
from app.models.project import (
    ApiInfo,
    ComplexityInfo,
    DependencyInfo,
    DocumentationInfo,
    ExistingTestInfo,
    ProjectMetrics,
    ProjectProfile,
)
from app.models.test_plan import EdgeCase, TestPlan, TestPlanSummary, TestSpec
from app.services.test_generator import generate_test_scaffolds
from app.core import config


def _make_profile(frameworks=None):
    return ProjectProfile(
        project_id="test",
        name="test",
        origin="path",
        created_at=datetime.now(timezone.utc),
        metrics=ProjectMetrics(
            total_files=5, source_files=3, test_files=2,
            documentation_files=0, configuration_files=0, other_files=0,
            total_lines=100, source_lines=100,
        ),
        tests=ExistingTestInfo(files=2, frameworks=frameworks or ["pytest"]),
        documentation=DocumentationInfo(files=0),
        dependencies=DependencyInfo(),
        api=ApiInfo(endpoints_detected=0),
        complexity=ComplexityInfo(level="Small"),
    )


def _make_codemap(functions=None, classes=None):
    functions = functions or []
    classes = classes or []
    return CodeMap(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        source_modules=[
            SourceModule(
                path="app.py", language="Python",
                functions=functions, classes=classes,
            )
        ],
    )


def _make_plan(specs, warnings=None):
    return TestPlan(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        specs=specs,
        summary=TestPlanSummary(
            total_specs=len(specs),
            critical_count=sum(1 for s in specs if s.priority == 1),
            high_count=sum(1 for s in specs if s.priority == 2),
            medium_count=sum(1 for s in specs if s.priority == 3),
            low_count=sum(1 for s in specs if s.priority in (4, 5)),
        ),
        warnings=warnings or [],
    )


def _make_spec(name="parse", target_type="function", priority=2, test_type="unit",
               edge_cases=None, is_async=False, target_file="app.py"):
    return TestSpec(
        target_qualified_name=name,
        target_file=target_file,
        target_type=target_type,
        priority=priority,
        test_type=test_type,
        suggested_test_name=f"test_{name.split('.')[-1]}_basic",
        edge_cases=edge_cases or [],
        risk_score=0.5,
    )


def test_single_target_generates_file():
    func = SourceFunction(
        name="parse", qualified_name="parse", file_path="app.py",
        line_start=1, line_end=5, args=["data"],
    )
    codemap = _make_codemap(functions=[func])
    spec = _make_spec()
    plan = _make_plan([spec])
    profile = _make_profile()

    result = generate_test_scaffolds(plan, codemap, profile)
    assert len(result.files) == 1
    assert result.files[0].file_path == "test_app.py"
    assert result.summary.total_test_functions >= 1


def test_multiple_targets_same_module():
    func_a = SourceFunction(
        name="a", qualified_name="a", file_path="app.py",
        line_start=1, line_end=3, args=[],
    )
    func_b = SourceFunction(
        name="b", qualified_name="b", file_path="app.py",
        line_start=4, line_end=6, args=["x"],
    )
    codemap = _make_codemap(functions=[func_a, func_b])
    specs = [_make_spec(name="a"), _make_spec(name="b")]
    plan = _make_plan(specs)

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    assert len(result.files) == 1
    assert result.files[0].target_count == 2


def test_edge_cases_generate_functions():
    func = SourceFunction(
        name="save", qualified_name="save", file_path="app.py",
        line_start=1, line_end=5, args=["path", "data"],
    )
    codemap = _make_codemap(functions=[func])
    edge_cases = [
        EdgeCase(parameter="path", case_type="empty", description="Empty path"),
        EdgeCase(parameter="data", case_type="none", description="None value"),
    ]
    spec = _make_spec(name="save", edge_cases=edge_cases)
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    content = result.files[0].content
    assert "test_save_edge_path_empty" in content
    assert "test_save_edge_data_none" in content
    assert result.summary.total_edge_cases == 2


def test_async_target_gets_decorator():
    func = SourceFunction(
        name="fetch", qualified_name="fetch", file_path="app.py",
        line_start=1, line_end=3, args=["url"], is_async=True,
    )
    codemap = _make_codemap(functions=[func])
    spec = _make_spec(name="fetch")
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    content = result.files[0].content
    assert "@pytest.mark.asyncio" in content
    assert "async def test_fetch_basic" in content


def test_method_target_class_based():
    method = SourceFunction(
        name="process", qualified_name="MyClass.process", file_path="app.py",
        line_start=10, line_end=15, args=["self", "data"],
    )
    cls = SourceClass(
        name="MyClass", qualified_name="MyClass", file_path="app.py",
        line_start=5, line_end=20, methods=[method],
    )
    codemap = _make_codemap(classes=[cls])
    spec = _make_spec(name="MyClass.process", target_type="method")
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    content = result.files[0].content
    assert "class TestMyClass:" in content
    assert "def setup_method" in content
    assert "test_process_basic" in content


def test_unittest_framework():
    func = SourceFunction(
        name="add", qualified_name="add", file_path="calc.py",
        line_start=1, line_end=3, args=["a", "b"],
    )
    codemap = CodeMap(
        project_id="test",
        created_at=datetime.now(timezone.utc),
        source_modules=[
            SourceModule(path="calc.py", language="Python", functions=[func])
        ],
    )
    spec = TestSpec(
        target_qualified_name="add", target_file="calc.py",
        target_type="function", priority=2, test_type="unit",
        suggested_test_name="test_add_basic", risk_score=0.3,
    )
    plan = _make_plan([spec])
    profile = _make_profile(frameworks=["unittest"])

    result = generate_test_scaffolds(plan, codemap, profile)
    content = result.files[0].content
    assert "import unittest" in content
    assert "unittest.TestCase" in content
    assert "if __name__" in content


def test_empty_plan():
    plan = _make_plan([])
    codemap = _make_codemap()
    profile = _make_profile()

    result = generate_test_scaffolds(plan, codemap, profile)
    assert len(result.files) == 0
    assert result.summary.total_files == 0
    assert result.summary.total_test_functions == 0


def test_deterministic_output():
    func = SourceFunction(
        name="process", qualified_name="process", file_path="app.py",
        line_start=1, line_end=5, args=["data", "config"],
    )
    codemap = _make_codemap(functions=[func])
    spec = _make_spec(name="process")
    plan = _make_plan([spec])
    profile = _make_profile()

    r1 = generate_test_scaffolds(plan, codemap, profile)
    r2 = generate_test_scaffolds(plan, codemap, profile)
    assert len(r1.files) == len(r2.files)
    for f1, f2 in zip(r1.files, r2.files):
        assert f1.content == f2.content
        assert f1.file_path == f2.file_path


def test_generated_code_valid_syntax():
    func = SourceFunction(
        name="parse", qualified_name="parse", file_path="app.py",
        line_start=1, line_end=5, args=["data", "path", "count"],
    )
    codemap = _make_codemap(functions=[func])
    edge_cases = [
        EdgeCase(parameter="path", case_type="empty", description="Empty path"),
    ]
    spec = _make_spec(name="parse", edge_cases=edge_cases)
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    for gf in result.files:
        ast.parse(gf.content)


def test_notimplemented_error_in_body():
    func = SourceFunction(
        name="run", qualified_name="run", file_path="app.py",
        line_start=1, line_end=3, args=[],
    )
    codemap = _make_codemap(functions=[func])
    spec = _make_spec(name="run")
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    assert 'raise NotImplementedError("Scaffold generated by AI Test Platform")' in result.files[0].content


def test_priority_range():
    func_a = SourceFunction(
        name="a", qualified_name="a", file_path="app.py",
        line_start=1, line_end=3, args=[],
    )
    func_b = SourceFunction(
        name="b", qualified_name="b", file_path="app.py",
        line_start=4, line_end=6, args=[],
    )
    codemap = _make_codemap(functions=[func_a, func_b])
    specs = [
        _make_spec(name="a", priority=1),
        _make_spec(name="b", priority=3),
    ]
    plan = _make_plan(specs)

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    assert result.files[0].priority_range == "1-3"


def test_summary_counts():
    func = SourceFunction(
        name="x", qualified_name="x", file_path="app.py",
        line_start=1, line_end=3, args=["a", "b", "c", "d"],
    )
    codemap = _make_codemap(functions=[func])
    spec = _make_spec(name="x", priority=1, test_type="unit")
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    assert result.summary.total_files == 1
    assert result.summary.total_test_functions >= 1
    assert result.summary.framework_used == "pytest"
    assert 1 in result.summary.by_priority


def test_no_timestamp_in_content():
    func = SourceFunction(
        name="foo", qualified_name="foo", file_path="app.py",
        line_start=1, line_end=3, args=[],
    )
    codemap = _make_codemap(functions=[func])
    spec = _make_spec(name="foo")
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    content = result.files[0].content
    assert "2026" not in content
    assert "2025" not in content


def test_edge_case_cap():
    func = SourceFunction(
        name="f", qualified_name="f", file_path="app.py",
        line_start=1, line_end=3, args=["x"],
    )
    codemap = _make_codemap(functions=[func])
    edges = [
        EdgeCase(parameter="x", case_type="none", description=f"case {i}")
        for i in range(30)
    ]
    spec = _make_spec(name="f", edge_cases=edges)
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    assert result.summary.total_edge_cases <= 20


def test_preconditions_in_docstring():
    func = SourceFunction(
        name="async_op", qualified_name="async_op", file_path="app.py",
        line_start=1, line_end=3, args=["url"], is_async=True,
    )
    codemap = _make_codemap(functions=[func])
    spec = TestSpec(
        target_qualified_name="async_op", target_file="app.py",
        target_type="function", priority=2, test_type="unit",
        suggested_test_name="test_async_op_basic",
        preconditions=["Requires an async test runner (pytest-asyncio)"],
        risk_score=0.5,
    )
    plan = _make_plan([spec])

    result = generate_test_scaffolds(plan, codemap, _make_profile())
    content = result.files[0].content
    assert "asyncio" in content.lower()


def test_empty_plan_returns_empty():
    plan = _make_plan([])
    codemap = CodeMap(
        project_id="empty",
        created_at=datetime.now(timezone.utc),
    )
    profile = _make_profile()

    result = generate_test_scaffolds(plan, codemap, profile)
    assert result.project_id == "test-project"
    assert len(result.files) == 0
    assert result.summary.total_files == 0


def test_preserves_plan_warnings():
    plan = _make_plan([], warnings=["Something went wrong"])
    codemap = _make_codemap()
    profile = _make_profile()

    result = generate_test_scaffolds(plan, codemap, profile)
    assert "Something went wrong" in result.warnings


def test_max_generated_files_cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_GENERATED_FILES", 2)
    specs = []
    funcs = []
    for i in range(5):
        fname = f"mod{i}"
        func = SourceFunction(
            name=f"fn{i}", qualified_name=f"fn{i}", file_path=f"{fname}.py",
            line_start=1, line_end=3, args=[],
        )
        funcs.append(func)
        specs.append(_make_spec(name=f"fn{i}", target_file=f"{fname}.py"))
    codemap = CodeMap(
        project_id="cap-test",
        created_at=datetime.now(timezone.utc),
        source_modules=[
            SourceModule(path=f"{fname}.py", language="Python", functions=[fn])
            for fname, fn in zip([f"mod{i}" for i in range(5)], funcs)
        ],
    )
    plan = _make_plan(specs)
    profile = _make_profile()

    result = generate_test_scaffolds(plan, codemap, profile)
    assert len(result.files) <= 2
    assert result.summary.total_files == len(result.files)
    assert any("truncated" in w.lower() for w in result.warnings)


def test_max_generated_functions_cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_GENERATED_FUNCTIONS", 3)
    specs = []
    funcs = []
    for i in range(6):
        fname = f"mod{i}"
        func = SourceFunction(
            name=f"fn{i}", qualified_name=f"fn{i}", file_path=f"{fname}.py",
            line_start=1, line_end=3, args=[],
        )
        funcs.append(func)
        specs.append(_make_spec(name=f"fn{i}", target_file=f"{fname}.py"))
    codemap = CodeMap(
        project_id="fncap",
        created_at=datetime.now(timezone.utc),
        source_modules=[
            SourceModule(path=f"{fname}.py", language="Python", functions=[fn])
            for fname, fn in zip([f"mod{i}" for i in range(6)], funcs)
        ],
    )
    plan = _make_plan(specs)
    profile = _make_profile()

    result = generate_test_scaffolds(plan, codemap, profile)
    assert result.summary.total_test_functions <= 3
    assert result.summary.total_files == len(result.files)
    for gf in result.files:
        ast.parse(gf.content)
    assert any("truncated" in w.lower() for w in result.warnings)


def test_max_scaffold_content_bytes_cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_SCAFFOLD_CONTENT_BYTES", 200)
    func = SourceFunction(
        name="big", qualified_name="big", file_path="app.py",
        line_start=1, line_end=3, args=[],
    )
    edges = [
        EdgeCase(parameter="x", case_type="none", description=f"case {i}")
        for i in range(10)
    ]
    codemap = _make_codemap(functions=[func])
    spec = _make_spec(name="big", edge_cases=edges)
    plan = _make_plan([spec])
    profile = _make_profile()

    result = generate_test_scaffolds(plan, codemap, profile)
    assert len(result.files) == 1
    assert any("exceeds" in w.lower() or "truncated" in w.lower()
               for w in result.warnings)
    content_bytes = len(result.files[0].content.encode("utf-8"))
    assert content_bytes <= config.MAX_SCAFFOLD_CONTENT_BYTES
    ast.parse(result.files[0].content)
