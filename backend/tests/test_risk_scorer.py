"""Tests for the rule-based risk scorer."""

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
    ComplexityInfo,
    ProjectMetrics,
    ProjectProfile,
    ExistingTestInfo,
    DocumentationInfo,
    DependencyInfo,
    ApiInfo,
)
from app.services.call_graph import CallGraph, build_call_graph
from app.services.risk_scorer import score_all, score_target
from datetime import datetime, timezone


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
        project_id="test",
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


def test_untested_function_high_risk():
    func = SourceFunction(
        name="parse", qualified_name="parse", file_path="app.py",
        line_start=1, line_end=5, args=["data", "config", "timeout", "verbose"],
    )
    target = TestableTarget(
        qualified_name="parse", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()
    cg = CallGraph()

    score = score_target(target, codemap, profile, cg)
    assert score >= 0.5  # no tests + many args = high risk


def test_well_tested_low_risk():
    func = SourceFunction(
        name="helper", qualified_name="helper", file_path="app.py",
        line_start=1, line_end=3, args=["self"],
        has_docstring=True,
    )
    target = TestableTarget(
        qualified_name="helper", file_path="app.py",
        target_type="function", has_tests=True, test_count=3,
    )
    mapping = TestMapping(
        test_function="test_helper", test_file="test_app.py",
        source_target="helper", source_file="app.py",
        confidence=0.9, method="name_similarity",
    )
    codemap = _make_codemap(
        functions=[func], targets=[target], mappings=[mapping],
    )
    profile = _make_profile()
    cg = CallGraph()
    cg.add_target("helper")

    score = score_target(target, codemap, profile, cg)
    assert score < 0.15  # well-tested + docstring = low risk


def test_public_method_boost():
    target = TestableTarget(
        qualified_name="MyClass.process", file_path="app.py",
        target_type="method", has_tests=False,
    )
    method = SourceFunction(
        name="process", qualified_name="MyClass.process", file_path="app.py",
        line_start=10, line_end=15, args=["self", "data"],
    )
    cls = SourceClass(
        name="MyClass", qualified_name="MyClass", file_path="app.py",
        line_start=5, line_end=20, methods=[method],
    )
    codemap = _make_codemap(classes=[cls], targets=[target])
    profile = _make_profile()
    cg = CallGraph()

    score = score_target(target, codemap, profile, cg)
    assert score >= 0.4


def test_private_method_lower_risk():
    target = TestableTarget(
        qualified_name="MyClass._internal", file_path="app.py",
        target_type="method", has_tests=False,
    )
    method = SourceFunction(
        name="_internal", qualified_name="MyClass._internal", file_path="app.py",
        line_start=10, line_end=12, args=["self"],
    )
    cls = SourceClass(
        name="MyClass", qualified_name="MyClass", file_path="app.py",
        line_start=5, line_end=20, methods=[method],
    )
    codemap = _make_codemap(classes=[cls], targets=[target])
    profile = _make_profile()
    cg = CallGraph()

    score = score_target(target, codemap, profile, cg)
    # Private method, no public method boost
    assert score < 0.5


def test_async_function_boost():
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
    cg = CallGraph()

    score = score_target(target, codemap, profile, cg)
    assert score >= 0.4


def test_high_complexity_project_boost():
    func = SourceFunction(
        name="x", qualified_name="x", file_path="app.py",
        line_start=1, line_end=2, args=["a"],
    )
    target = TestableTarget(
        qualified_name="x", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile(complexity="Large")
    cg = CallGraph()

    score_large = score_target(target, codemap, profile, cg)

    profile_small = _make_profile(complexity="Small")
    score_small = score_target(target, codemap, profile_small, cg)

    assert score_large > score_small


def test_fan_in_boost():
    func = SourceFunction(
        name="shared", qualified_name="shared", file_path="app.py",
        line_start=1, line_end=2, args=[],
    )
    target = TestableTarget(
        qualified_name="shared", file_path="app.py",
        target_type="function", has_tests=True, test_count=2,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile()

    cg_high = CallGraph()
    cg_high.add_target("shared")
    for i in range(6):
        cg_high.add_target(f"caller{i}")
        cg_high.add_call(f"caller{i}", "shared")

    score_high = score_target(target, codemap, profile, cg_high)

    cg_low = CallGraph()
    cg_low.add_target("shared")

    score_low = score_target(target, codemap, profile, cg_low)

    assert score_high > score_low


def test_low_confidence_mapping_boost():
    func = SourceFunction(
        name="x", qualified_name="x", file_path="app.py",
        line_start=1, line_end=2, args=["a"],
    )
    target = TestableTarget(
        qualified_name="x", file_path="app.py",
        target_type="function", has_tests=True, test_count=1,
    )
    mapping = TestMapping(
        test_function="test_something", test_file="test_app.py",
        source_target="x", source_file="app.py",
        confidence=0.3, method="name_similarity",
    )
    codemap = _make_codemap(
        functions=[func], targets=[target], mappings=[mapping],
    )
    profile = _make_profile()
    cg = CallGraph()

    score = score_target(target, codemap, profile, cg)
    assert score > 0.0


def test_score_all_returns_dict():
    func1 = SourceFunction(
        name="a", qualified_name="a", file_path="app.py",
        line_start=1, line_end=2, args=[],
    )
    func2 = SourceFunction(
        name="b", qualified_name="b", file_path="app.py",
        line_start=3, line_end=4, args=["x"],
    )
    targets = [
        TestableTarget(qualified_name="a", file_path="app.py", target_type="function", has_tests=False),
        TestableTarget(qualified_name="b", file_path="app.py", target_type="function", has_tests=True, test_count=2),
    ]
    codemap = _make_codemap(functions=[func1, func2], targets=targets)
    profile = _make_profile()
    cg = CallGraph()

    scores = score_all(codemap, profile, cg)
    assert "a" in scores
    assert "b" in scores
    assert scores["a"] > scores["b"]  # untested > well-tested


def test_score_bounded():
    func = SourceFunction(
        name="x", qualified_name="x", file_path="app.py",
        line_start=1, line_end=2, args=["a", "b", "c", "d", "e"],
        is_async=True,
    )
    target = TestableTarget(
        qualified_name="x", file_path="app.py",
        target_type="function", has_tests=False,
    )
    codemap = _make_codemap(functions=[func], targets=[target])
    profile = _make_profile(complexity="Large")
    cg = CallGraph()

    score = score_target(target, codemap, profile, cg)
    assert 0.0 <= score <= 1.0
