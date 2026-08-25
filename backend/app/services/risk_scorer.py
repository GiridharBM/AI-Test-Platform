"""Rule-based risk scoring for testable targets.

Computes a 0.0–1.0 risk score for each TestableTarget using configurable
weights and deterministic signals from the CodeMap and ProjectProfile.
"""

from app.core import config
from app.models.codemap import CodeMap, TestableTarget
from app.models.project import ProjectProfile
from app.services.call_graph import CallGraph


def score_target(
    target: TestableTarget,
    codemap: CodeMap,
    profile: ProjectProfile,
    call_graph: CallGraph,
) -> float:
    """Compute a risk score (0.0–1.0) for a single testable target.

    Higher score = higher risk = higher test priority.
    """
    score = 0.0

    # No tests at all
    if not target.has_tests:
        score += config.RISK_WEIGHT_NO_TESTS

    # High argument count (≥4 args is elevated risk)
    func = _find_source_function(target, codemap)
    if func and len(func.args) >= 4:
        score += config.RISK_WEIGHT_ARG_COUNT
    elif func and len(func.args) >= 2:
        score += config.RISK_WEIGHT_ARG_COUNT * 0.5

    # Async functions
    if func and func.is_async:
        score += config.RISK_WEIGHT_ASYNC

    # No docstring
    if func and not func.has_docstring:
        score += config.RISK_WEIGHT_NO_DOCSTRING

    # Public method (no _ prefix) on a class
    if target.target_type == "method":
        bare_name = target.qualified_name.rsplit(".", 1)[-1]
        if not bare_name.startswith("_"):
            score += config.RISK_WEIGHT_PUBLIC_METHOD

    # High project complexity
    if profile.complexity.level == "Large":
        score += config.RISK_WEIGHT_HIGH_COMPLEXITY
    elif profile.complexity.level == "Medium":
        score += config.RISK_WEIGHT_HIGH_COMPLEXITY * 0.5

    # Low-confidence test mapping
    low_conf_mappings = [
        m for m in codemap.test_mappings
        if m.source_target == target.qualified_name and m.confidence < 0.5
    ]
    if low_conf_mappings:
        score += config.RISK_WEIGHT_LOW_CONFIDENCE_MAP

    # Fan-in boost: if many callers depend on this function, it's higher risk
    fan_in = call_graph.fan_in(target.qualified_name)
    if fan_in >= 5:
        score = min(score + 0.15, 1.0)
    elif fan_in >= 2:
        score = min(score + 0.08, 1.0)

    return round(min(score, 1.0), 3)


def score_all(
    codemap: CodeMap,
    profile: ProjectProfile,
    call_graph: CallGraph,
) -> dict[str, float]:
    """Score all testable targets. Returns {qualified_name: risk_score}."""
    return {
        t.qualified_name: score_target(t, codemap, profile, call_graph)
        for t in codemap.testable_targets
    }


def _find_source_function(
    target: TestableTarget,
    codemap: CodeMap,
):
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
