"""Project-level test discovery orchestrator.

Reads a profiled project's source tree, runs Python ast analysis on each
source and test file, builds a CodeMap, and persists it. Deterministic,
read-only, no code execution.
"""

from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.models.codemap import (
    CodeMap,
    CoverageSummary,
    SourceModule,
    TestFunction,
    TestableTarget,
)
from app.services import code_analyzer
from app.services import test_discovery


def discover_project(
    project_id: str,
    workspace: Path | None = None,
) -> CodeMap:
    """Run deterministic test discovery on a profiled project.

    Reads the project source tree, parses Python files with ast,
    discovers test functions, maps tests to source targets, and
    returns a full CodeMap. Results are persisted by the caller.
    """
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    meta = ingestion.read_meta(ws, project_id)
    root = Path(meta.source_path) if meta.origin == "path" else ingestion.source_dir(ws, project_id)

    if not root.is_dir():
        raise ValueError(f"Project source is missing: {root}")

    source_modules: list[SourceModule] = []
    test_functions: list[TestFunction] = []
    test_imports: dict[str, set[str]] = {}
    warnings: list[str] = []

    # Walk the tree deterministically (sorted)
    py_files = sorted(
        p for p in root.rglob("*.py")
        if _should_analyze(p, root)
    )

    for path in py_files:
        rel = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            warnings.append(f"Could not read {rel}: {exc}")
            continue

        is_test = _is_test_path(rel)

        if is_test:
            tf, tf_warns = test_discovery.discover_test_functions(rel, content)
            test_functions.extend(tf)
            warnings.extend(tf_warns)
            # Collect test file imports for import-analysis mapping
            try:
                import ast as _ast
                tree = _ast.parse(content)
                imports = set()
                for node in _ast.iter_child_nodes(tree):
                    if isinstance(node, _ast.Import):
                        for alias in node.names:
                            imports.add(alias.name)
                    elif isinstance(node, _ast.ImportFrom):
                        if node.module:
                            imports.add(node.module)
                if imports:
                    test_imports[rel] = imports
            except (SyntaxError, ValueError):
                pass
            if len(test_functions) > config.MAX_TEST_FUNCTIONS:
                test_functions = test_functions[: config.MAX_TEST_FUNCTIONS]
                warnings.append(
                    f"Test function count exceeded {config.MAX_TEST_FUNCTIONS}; truncated."
                )
                break
        else:
            mod, mod_warns = code_analyzer.analyze_source_file(rel, content)
            source_modules.append(mod)
            warnings.extend(mod_warns)

    # Mapping and target building
    mappings = test_discovery.map_tests_to_sources(
        test_functions, source_modules, test_import_index=test_imports
    )
    if len(mappings) > config.MAX_MAPPING_ENTRIES:
        mappings = mappings[: config.MAX_MAPPING_ENTRIES]
        warnings.append(
            f"Mapping count exceeded {config.MAX_MAPPING_ENTRIES}; truncated."
        )

    targets = test_discovery.build_testable_targets(source_modules, test_functions, mappings)
    if len(targets) > config.MAX_TESTABLE_TARGETS:
        targets = targets[: config.MAX_TESTABLE_TARGETS]
        warnings.append(
            f"Target count exceeded {config.MAX_TESTABLE_TARGETS}; truncated."
        )

    coverage = _build_coverage_summary(targets, source_modules)

    return CodeMap(
        project_id=project_id,
        created_at=datetime.now(timezone.utc),
        source_modules=source_modules,
        test_functions=test_functions,
        test_mappings=mappings,
        testable_targets=targets,
        coverage_summary=coverage,
        warnings=warnings,
    )


def _should_analyze(path: Path, root: Path) -> bool:
    """Return True if the file should be analyzed (inside root, not in ignored dir)."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    parts = path.relative_to(root).parts
    return not any(part in config.IGNORED_DIRS for part in parts)


def _is_test_path(rel_path: str) -> bool:
    """Determine if a file path is a test file based on conventions."""
    name = rel_path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    parent_parts = rel_path.split("/")[:-1]
    return any(p.lower() in {"tests", "test", "__tests__", "spec"} for p in parent_parts)


def _build_coverage_summary(
    targets: list[TestableTarget],
    modules: list[SourceModule],
) -> CoverageSummary:
    """Build aggregate coverage statistics."""
    total = len(targets)
    with_tests = sum(1 for t in targets if t.has_tests)
    without_tests = total - with_tests
    untested = [t.qualified_name for t in targets if not t.has_tests]

    return CoverageSummary(
        total_targets=total,
        targets_with_tests=with_tests,
        targets_without_tests=without_tests,
        coverage_percentage=round(with_tests * 100.0 / total, 1) if total else 0.0,
        untested_functions=untested,
    )
