"""Tests for the deterministic test plan generator."""

from datetime import datetime, timezone

from app.models.codemap import (
    CodeMap,
    CoverageSummary,
    SourceClass,
    SourceFunction,
    SourceModule,
    TestFunction,
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
from app.services.call_graph import CallGraph
from app.services.test_planner import generate_test_plan


def _make_profile(complexity: str = "Small") -> ProjectProfile:
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
        tests=ExistingTestInfo(files=2),
        documentation=DocumentationInfo(files=0),
        dependencies=DependencyInfo(),
        api=ApiInfo(endpoints_detected=0),
        complexity=ComplexityInfo(level=complexity),
    )


def _make_codemap(functions=None, classes=None, targets=None, mappings=None):
    functions = functions or []
    classes = classes or []
    targets = targets or []
    mappings = mappings or []
    return CodeMap(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        source_modules=[
            SourceModule(
                path="app.py", language="Python",
                functions=functions, classes=classes,
            )
        ],
        testable_targets=targets,
        test_mappings=mappings,
        coverage_summary=CoverageSummary(
            total_targets=len(targets),
            targets_with_tests=sum(1 for t in targets if t.has_tests),
            targets_without_tests=sum(1 for t in targets if not t.has_tests),
            coverage_percentage=0.0,
        ),
    )


def test_plan_basic_structure():
    target = TestableTarget(
        qualified_name="parse", file_path="app.py",
        target_type="function", has_tests=False,
    )
    func = SourceFunction(
        name="parse", qualified_name="parse", file_path="app.py",
        line_start=1, line_end=5, args=["data"],
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    assert plan.project_id == "test-project"
    assert len(plan.specs) >= 1
    assert plan.summary.total_specs >= 1
    assert plan.created_at is not None


def test_plan_skips_well_tested_targets():
    func = SourceFunction(
        name="helper", qualified_name="helper", file_path="app.py",
        line_start=1, line_end=3, args=["self"],
        has_docstring=True,
    )
    target = TestableTarget(
        qualified_name="helper", file_path="app.py",
        target_type="function", has_tests=True, test_count=3,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    # Well-tested target with 3 tests and docstring should be skipped
    spec_names = [s.target_qualified_name for s in plan.specs]
    assert "helper" not in spec_names


def test_plan_generates_spec_for_untested():
    func = SourceFunction(
        name="process", qualified_name="process", file_path="app.py",
        line_start=1, line_end=5, args=["data", "config"],
    )
    target = TestableTarget(
        qualified_name="process", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    assert len(plan.specs) == 1
    spec = plan.specs[0]
    assert spec.target_qualified_name == "process"
    assert spec.priority >= 1
    assert spec.test_type == "unit"
    assert "test_process" in spec.suggested_test_name


def test_plan_priority_ordering():
    func_a = SourceFunction(
        name="critical", qualified_name="critical", file_path="app.py",
        line_start=1, line_end=5, args=["a", "b", "c", "d"],
    )
    func_b = SourceFunction(
        name="simple", qualified_name="simple", file_path="app.py",
        line_start=6, line_end=8, args=["self"],
        has_docstring=True,
    )
    target_a = TestableTarget(
        qualified_name="critical", file_path="app.py",
        target_type="function", has_tests=False,
    )
    target_b = TestableTarget(
        qualified_name="simple", file_path="app.py",
        target_type="function", has_tests=True, test_count=1,
    )
    mapping = TestMapping(
        test_function="test_simple", test_file="test_app.py",
        source_target="simple", source_file="app.py",
        confidence=0.8, method="name_similarity",
    )
    codemap = _make_codemap(
        functions=[func_a, func_b],
        targets=[target_a, target_b],
        mappings=[mapping],
    )
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    # critical (untested, many args) should come first
    if len(plan.specs) >= 2:
        assert plan.specs[0].target_qualified_name == "critical"


def test_plan_edge_cases_generated():
    func = SourceFunction(
        name="save", qualified_name="save", file_path="app.py",
        line_start=1, line_end=5, args=["path", "data", "count"],
    )
    target = TestableTarget(
        qualified_name="save", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    spec = plan.specs[0]
    assert len(spec.edge_cases) >= 1
    params_with_cases = {ec.parameter for ec in spec.edge_cases}
    assert "path" in params_with_cases
    assert "count" in params_with_cases


def test_plan_preconditions_for_async():
    func = SourceFunction(
        name="fetch", qualified_name="fetch", file_path="app.py",
        line_start=1, line_end=3, args=["url"], is_async=True,
    )
    target = TestableTarget(
        qualified_name="fetch", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    spec = plan.specs[0]
    assert any("async" in p.lower() for p in spec.preconditions)


def test_plan_summary_counts():
    funcs = [
        SourceFunction(
            name=f"func{i}", qualified_name=f"func{i}", file_path="app.py",
            line_start=i, line_end=i + 1, args=["a", "b", "c", "d"],
        )
        for i in range(5)
    ]
    targets = [
        TestableTarget(
            qualified_name=f"func{i}", file_path="app.py",
            target_type="function", has_tests=False,
        )
        for i in range(5)
    ]
    codemap = _make_codemap(functions=funcs, targets=targets)
    profile = _make_profile(complexity="Large")

    plan = generate_test_plan(codemap, profile)
    assert plan.summary.total_specs == 5
    assert plan.summary.critical_count + plan.summary.high_count + plan.summary.medium_count + plan.summary.low_count == 5
    assert "unit" in plan.summary.by_type


def test_plan_deterministic():
    func = SourceFunction(
        name="x", qualified_name="x", file_path="app.py",
        line_start=1, line_end=3, args=["a", "b"],
    )
    target = TestableTarget(
        qualified_name="x", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    plan1 = generate_test_plan(codemap, profile)
    plan2 = generate_test_plan(codemap, profile)

    assert plan1.summary.total_specs == plan2.summary.total_specs
    assert len(plan1.specs) == len(plan2.specs)
    for s1, s2 in zip(plan1.specs, plan2.specs):
        assert s1.target_qualified_name == s2.target_qualified_name
        assert s1.risk_score == s2.risk_score
        assert s1.priority == s2.priority


def test_plan_with_empty_codemap():
    codemap = CodeMap(
        project_id="empty",
        created_at=datetime.now(timezone.utc),
    )
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    assert plan.project_id == "empty"
    assert len(plan.specs) == 0
    assert plan.summary.total_specs == 0


def test_plan_with_call_graph_fan_in():
    func = SourceFunction(
        name="shared", qualified_name="shared", file_path="app.py",
        line_start=1, line_end=2, args=["x"],
    )
    target = TestableTarget(
        qualified_name="shared", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    cg = CallGraph()
    cg.add_target("shared")
    for i in range(6):
        cg.add_target(f"caller{i}")
        cg.add_call(f"caller{i}", "shared")

    plan = generate_test_plan(codemap, profile, call_graph=cg)
    # shared has high fan-in so should have high risk
    spec = plan.specs[0]
    assert spec.risk_score >= 0.5


def test_plan_method_target():
    method = SourceFunction(
        name="process", qualified_name="MyClass.process", file_path="app.py",
        line_start=10, line_end=15, args=["self", "data"],
    )
    cls = SourceClass(
        name="MyClass", qualified_name="MyClass", file_path="app.py",
        line_start=5, line_end=20, methods=[method],
    )
    target = TestableTarget(
        qualified_name="MyClass.process", file_path="app.py",
        target_type="method", has_tests=False,
    )
    codemap = _make_codemap(classes=[cls], targets=[target])
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    spec = plan.specs[0]
    assert spec.target_type == "method"
    assert any("class" in p.lower() or "instantiation" in p.lower() for p in spec.preconditions)


def test_plan_related_tested_targets():
    func_a = SourceFunction(
        name="a", qualified_name="a", file_path="app.py",
        line_start=1, line_end=3, args=["x"],
    )
    func_b = SourceFunction(
        name="b", qualified_name="b", file_path="app.py",
        line_start=4, line_end=6, args=["y"],
    )
    target_a = TestableTarget(
        qualified_name="a", file_path="app.py",
        target_type="function", has_tests=False,
    )
    target_b = TestableTarget(
        qualified_name="b", file_path="app.py",
        target_type="function", has_tests=True, test_count=2,
    )
    codemap = _make_codemap(
        functions=[func_a, func_b],
        targets=[target_a, target_b],
    )
    profile = _make_profile()

    plan = generate_test_plan(codemap, profile)
    spec_a = next(s for s in plan.specs if s.target_qualified_name == "a")
    assert "b" in spec_a.related_tested_targets


def test_plan_negative_test_type():
    func = SourceFunction(
        name="strict", qualified_name="strict", file_path="app.py",
        line_start=1, line_end=5, args=["a"],
    )
    target = TestableTarget(
        qualified_name="strict", file_path="app.py",
        target_type="function", has_tests=True, test_count=1,
    )
    mapping = TestMapping(
        test_function="test_strict", test_file="test_app.py",
        source_target="strict", source_file="app.py",
        confidence=0.3, method="name_similarity",
    )
    codemap = _make_codemap(
        functions=[func], targets=[target], mappings=[mapping],
    )
    profile = _make_profile(complexity="Large")

    plan = generate_test_plan(codemap, profile)
    spec = next(s for s in plan.specs if s.target_qualified_name == "strict")
    assert spec.test_type in ("edge_case", "negative", "unit")
