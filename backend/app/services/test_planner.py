"""Deterministic test plan generator.

Orchestrates risk scoring, edge-case inference, and test specification
assembly into a prioritised TestPlan. No LLM, no code execution.
"""

from datetime import datetime, timezone

from app.core import config
from app.models.codemap import CodeMap, SourceFunction, TestableTarget
from app.models.project import ProjectProfile
from app.models.test_plan import EdgeCase, TestPlan, TestPlanSummary, TestSpec
from app.services.call_graph import CallGraph
from app.services.risk_scorer import score_all


def generate_test_plan(
    codemap: CodeMap,
    profile: ProjectProfile,
    call_graph: CallGraph | None = None,
) -> TestPlan:
    """Generate a prioritised test plan from the code map and profile.

    Args:
        codemap: The project's code map.
        profile: The project's profile.
        call_graph: Pre-built call graph. If None, an empty graph is used
                    (risk scoring falls back to non-graph signals).
    """
    warnings = list(codemap.warnings)
    cg = call_graph or CallGraph()

    # Score all targets
    risk_scores = score_all(codemap, profile, cg)

    # Build index of tested targets for related_tested_targets lookup
    tested_targets = {
        t.qualified_name for t in codemap.testable_targets if t.has_tests
    }

    # Build per-module tested targets lookup
    module_tested: dict[str, list[str]] = {}
    for t in codemap.testable_targets:
        if t.has_tests:
            module_tested.setdefault(t.file_path, []).append(t.qualified_name)

    # Generate specs for targets needing tests (or with weak test coverage)
    specs: list[TestSpec] = []
    for target in codemap.testable_targets:
        if target.has_tests and target.test_count >= 2:
            continue  # well-tested, skip

        risk = risk_scores.get(target.qualified_name, 0.0)
        if risk < 0.05 and target.has_tests:
            continue  # very low risk and has tests, skip

        func = _find_source(target, codemap)
        spec = _build_spec(
            target, func, risk, codemap, module_tested, tested_targets
        )
        specs.append(spec)

    # Cap specs
    if len(specs) > config.MAX_TEST_SPECS:
        warnings.append(
            f"Test spec count exceeded {config.MAX_TEST_SPECS}; truncated."
        )
        specs = specs[: config.MAX_TEST_SPECS]

    # Sort: highest risk first, then alphabetically for stability
    specs.sort(key=lambda s: (-s.risk_score, s.target_qualified_name))

    summary = _build_summary(specs, codemap)

    return TestPlan(
        project_id=codemap.project_id,
        created_at=datetime.now(timezone.utc),
        specs=specs,
        summary=summary,
        warnings=warnings,
    )


def _build_spec(
    target: TestableTarget,
    func: SourceFunction | None,
    risk: float,
    codemap: CodeMap,
    module_tested: dict[str, list[str]],
    tested_targets: set[str],
) -> TestSpec:
    """Build a single TestSpec for a testable target."""
    priority = _risk_to_priority(risk)
    test_type = _infer_test_type(target, risk)
    edge_cases = _infer_edge_cases(func) if func else []
    preconditions = _infer_preconditions(func, target) if func else []
    related = module_tested.get(target.file_path, [])
    related = [r for r in related if r != target.qualified_name][:5]

    bare_name = target.qualified_name.rsplit(".", 1)[-1]
    suggested_name = f"test_{bare_name}_success"
    if not target.has_tests:
        suggested_name = f"test_{bare_name}_basic"
    if test_type == "edge_case":
        suggested_name = f"test_{bare_name}_edge_cases"
    elif test_type == "negative":
        suggested_name = f"test_{bare_name}_error_handling"

    return TestSpec(
        target_qualified_name=target.qualified_name,
        target_file=target.file_path,
        target_type=target.target_type,
        priority=priority,
        test_type=test_type,
        suggested_test_name=suggested_name,
        preconditions=preconditions,
        edge_cases=edge_cases,
        related_tested_targets=related,
        risk_score=risk,
    )


def _risk_to_priority(risk: float) -> int:
    if risk >= 0.7:
        return 1
    if risk >= 0.5:
        return 2
    if risk >= 0.3:
        return 3
    if risk >= 0.1:
        return 4
    return 5


def _infer_test_type(target: TestableTarget, risk: float) -> str:
    if not target.has_tests:
        return "unit"
    if target.test_count == 1 and risk >= 0.4:
        return "edge_case"
    if risk >= 0.6:
        return "negative"
    return "unit"


def _infer_edge_cases(func: SourceFunction | None) -> list[EdgeCase]:
    """Generate edge case suggestions based on parameter names and types."""
    if not func or not func.args:
        return []

    cases: list[EdgeCase] = []
    for arg in func.args:
        # Skip self/cls
        if arg in ("self", "cls"):
            continue
        bare = arg.lstrip("*")

        # Heuristic matching on parameter names
        if bare in ("path", "filepath", "file_path", "dir", "directory"):
            cases.append(EdgeCase(
                parameter=arg, case_type="empty",
                description="Empty string path",
            ))
            cases.append(EdgeCase(
                parameter=arg, case_type="boundary",
                description="Very long path (>1000 chars)",
            ))
        elif bare in ("name", "filename", "file_name", "username", "title"):
            cases.append(EdgeCase(
                parameter=arg, case_type="empty",
                description="Empty string",
            ))
            cases.append(EdgeCase(
                parameter=arg, case_type="boundary",
                description="Very long string (>500 chars)",
            ))
        elif bare in ("count", "num", "number", "size", "limit", "offset", "page"):
            cases.append(EdgeCase(
                parameter=arg, case_type="negative",
                description="Negative value",
            ))
            cases.append(EdgeCase(
                parameter=arg, case_type="boundary",
                description="Zero",
            ))
        elif bare in ("data", "payload", "body", "content", "input"):
            cases.append(EdgeCase(
                parameter=arg, case_type="none",
                description="None value",
            ))
            cases.append(EdgeCase(
                parameter=arg, case_type="empty",
                description="Empty container (empty dict/list/string)",
            ))
        elif bare in ("timeout", "retries", "max_retries", "attempts"):
            cases.append(EdgeCase(
                parameter=arg, case_type="boundary",
                description="Zero",
            ))
            cases.append(EdgeCase(
                parameter=arg, case_type="negative",
                description="Negative value",
            ))
        elif bare in ("enabled", "flag", "verbose", "debug", "force"):
            cases.append(EdgeCase(
                parameter=arg, case_type="boolean",
                description="Test both True and False",
            ))
        elif bare.startswith("*"):
            cases.append(EdgeCase(
                parameter=arg, case_type="boundary",
                description="No extra arguments provided",
            ))
        elif bare.startswith("**"):
            cases.append(EdgeCase(
                parameter=arg, case_type="boundary",
                description="No extra keyword arguments provided",
            ))
        else:
            # Generic: test with None
            cases.append(EdgeCase(
                parameter=arg, case_type="none",
                description="None value",
            ))

    return cases


def _infer_preconditions(
    func: SourceFunction | None,
    target: TestableTarget,
) -> list[str]:
    """Infer preconditions from decorators and function characteristics."""
    if not func:
        return []

    preconditions: list[str] = []

    if func.is_async:
        preconditions.append("Requires an async test runner (pytest-asyncio)")

    for dec in func.decorators:
        if "skip" in dec.lower():
            preconditions.append(f"Conditionally skipped: {dec}")
        if "slow" in dec.lower():
            preconditions.append("Marked as slow; may need timeout configuration")
        if "mock" in dec.lower() or "patch" in dec.lower():
            preconditions.append("May require mocking external dependencies")

    if target.target_type == "method":
        preconditions.append("Requires class instantiation")

    return preconditions


def _find_source(target: TestableTarget, codemap: CodeMap):
    """Find the SourceFunction/SourceClass matching a TestableTarget."""
    qn = target.qualified_name
    for mod in codemap.source_modules:
        for func in mod.functions:
            if func.qualified_name == qn:
                return func
        for cls in mod.classes:
            if cls.qualified_name == qn:
                return cls
            for method in cls.methods:
                if method.qualified_name == qn:
                    return method
    return None


def _build_summary(specs: list[TestSpec], codemap: CodeMap) -> TestPlanSummary:
    """Build aggregate summary statistics."""
    by_type: dict[str, int] = {}
    for s in specs:
        by_type[s.test_type] = by_type.get(s.test_type, 0) + 1

    untested_modules = sorted({
        t.file_path
        for t in codemap.testable_targets
        if not t.has_tests
    })

    return TestPlanSummary(
        total_specs=len(specs),
        critical_count=sum(1 for s in specs if s.priority == 1),
        high_count=sum(1 for s in specs if s.priority == 2),
        medium_count=sum(1 for s in specs if s.priority == 3),
        low_count=sum(1 for s in specs if s.priority in (4, 5)),
        by_type=by_type,
        untested_modules=untested_modules,
    )
