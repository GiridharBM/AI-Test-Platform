"""Test function discovery and test-to-source mapping.

Parses test files to extract individual test functions, detects assertion
patterns, and heuristically maps tests to source targets. Read-only,
deterministic, no code execution.
"""

import ast
import re
from pathlib import Path, PurePosixPath

from app.core import config
from app.models.codemap import SourceModule, TestFunction, TestMapping, TestableTarget

_ASSERT_CALL_RE = re.compile(
    r"""\b(?:assert(?:Equal|NotEqual|True|False|Is|IsNot|In|NotIn|Raises|Warns|"
    r"Approx|Less|LessEqual|Greater|GreaterEqual)?|expect)\s*[\(]""",
    re.VERBOSE,
)
_ASSERT_BARE_RE = re.compile(r"""\bassert\s+""", re.VERBOSE)


def discover_test_functions(
    path: str,
    content: str,
) -> tuple[list[TestFunction], list[str]]:
    """Parse a test file and extract test function metadata."""
    warnings: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        warnings.append(f"Test file could not be parsed: {path} ({exc})")
        return [], warnings

    test_funcs: list[TestFunction] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_test_function(node.name):
                continue
            body_src = ast.get_source_segment(content, node) or ""
            assertion_count = len(_ASSERT_CALL_RE.findall(body_src))
            assertion_count += len(_ASSERT_BARE_RE.findall(body_src))
            test_funcs.append(TestFunction(
                name=node.name,
                file_path=path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                decorators=[_extract_decorator_str(d) for d in node.decorator_list],
                has_docstring=ast.get_docstring(node) is not None,
                assertion_count=assertion_count,
            ))

    return test_funcs, warnings


def _is_test_function(name: str) -> bool:
    return name.startswith("test_") or name.endswith("_test")


def _extract_decorator_str(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        n: ast.expr = node
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
        return ".".join(reversed(parts))
    if isinstance(node, ast.Call):
        return _extract_decorator_str(node.func)
    return ast.dump(node)


def map_tests_to_sources(
    test_functions: list[TestFunction],
    source_modules: list[SourceModule],
    test_import_index: dict[str, set[str]] | None = None,
) -> list[TestMapping]:
    """Heuristically map test functions to source targets.

    Strategy:
    1. Name similarity: strip test_/test prefix and _test suffix, compare
       to source function/class names.
    2. Import analysis: if test file imports a module containing the source
       target, boost confidence.

    Returns mappings sorted by confidence descending.
    """
    # Build lookup structures
    source_names: dict[str, tuple[str, str]] = {}  # lower_name → (qualified_name, file_path)
    for mod in source_modules:
        for func in mod.functions:
            key = func.name.lower().lstrip("_")
            source_names[key] = (func.qualified_name, mod.path)
        for cls in mod.classes:
            key = cls.name.lower().lstrip("_")
            source_names[key] = (cls.qualified_name, mod.path)
            for method in cls.methods:
                mkey = method.name.lower().lstrip("_")
                if mkey not in source_names:
                    source_names[mkey] = (method.qualified_name, mod.path)

    # Build import index: file_path → set of imported module names
    import_index: dict[str, set[str]] = {}
    for mod in source_modules:
        import_index[mod.path] = set(mod.imports)
    if test_import_index:
        for path, imports in test_import_index.items():
            import_index.setdefault(path, set()).update(imports)

    mappings: list[TestMapping] = []

    for tf in test_functions:
        stripped = _strip_test_prefix_suffix(tf.name).lower()
        best_conf = 0.0
        best_target = ""
        best_file = ""
        best_method = "none"

        # Name similarity
        if stripped in source_names:
            target_name, target_file = source_names[stripped]
            best_conf = 0.8
            best_target = target_name
            best_file = target_file
            best_method = "name_similarity"
        else:
            # Partial match: check if stripped is a substring of any source name
            for sname, (tname, tfile) in source_names.items():
                if stripped in sname or sname in stripped:
                    if best_conf < 0.5:
                        best_conf = 0.5
                        best_target = tname
                        best_file = tfile
                        best_method = "name_similarity"

        # Import analysis boost
        if best_conf > 0.0 and tf.file_path in import_index:
            imported = import_index[tf.file_path]
            for mod_name in imported:
                mod_lower = mod_name.lower()
                if best_target and mod_lower in best_target.lower():
                    best_conf = min(best_conf + 0.1, 1.0)
                    best_method = "import_analysis"

        if best_conf >= 0.3:
            mappings.append(TestMapping(
                test_function=tf.name,
                test_file=tf.file_path,
                source_target=best_target,
                source_file=best_file,
                confidence=round(best_conf, 2),
                method=best_method,
            ))

    mappings.sort(key=lambda m: (-m.confidence, m.test_function))
    return mappings


def _strip_test_prefix_suffix(name: str) -> str:
    """Remove test_ prefix and _test suffix to get the likely source name."""
    result = name
    if result.startswith("test_"):
        result = result[5:]
    if result.endswith("_test"):
        result = result[:-5]
    return result


def build_testable_targets(
    source_modules: list[SourceModule],
    test_functions: list[TestFunction],
    test_mappings: list[TestMapping],
) -> list[TestableTarget]:
    """Build the list of testable entities with coverage info."""
    # Index mappings by source target
    target_tests: dict[str, list[tuple[str, str]]] = {}  # target → [(test_name, test_file)]
    for m in test_mappings:
        target_tests.setdefault(m.source_target, []).append(
            (m.test_function, m.test_file)
        )

    targets: list[TestableTarget] = []

    for mod in source_modules:
        for func in mod.functions:
            qn = func.qualified_name
            covering = target_tests.get(qn, [])
            targets.append(TestableTarget(
                qualified_name=qn,
                file_path=mod.path,
                target_type="function",
                has_tests=len(covering) > 0,
                test_count=len(covering),
                test_files=sorted({f for _, f in covering}),
                mapped_tests=sorted({t for t, _ in covering}),
            ))
        for cls in mod.classes:
            qn = cls.qualified_name
            covering = target_tests.get(qn, [])
            for method in cls.methods:
                mq = method.qualified_name
                m_covering = target_tests.get(mq, [])
                covering = covering + m_covering
            all_test_files = sorted({f for _, f in covering})
            all_test_names = sorted({t for t, _ in covering})
            targets.append(TestableTarget(
                qualified_name=qn,
                file_path=mod.path,
                target_type="class",
                has_tests=len(covering) > 0,
                test_count=len(covering),
                test_files=all_test_files,
                mapped_tests=all_test_names,
            ))
            for method in cls.methods:
                mq = method.qualified_name
                m_covering = target_tests.get(mq, [])
                targets.append(TestableTarget(
                    qualified_name=mq,
                    file_path=mod.path,
                    target_type="method",
                    has_tests=len(m_covering) > 0,
                    test_count=len(m_covering),
                    test_files=sorted({f for _, f in m_covering}),
                    mapped_tests=sorted({t for t, _ in m_covering}),
                ))

    return targets
