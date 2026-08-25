"""Deterministic test scaffold generator.

Produces syntactically valid Python test files from a TestPlan, CodeMap,
and ProjectProfile. Pure template-based — no LLM, no code execution.
Generated files use NotImplementedError placeholders for human/AI completion.
"""

from datetime import datetime, timezone

from app.core import config
from app.models.codemap import CodeMap, SourceClass, SourceFunction
from app.models.project import ProjectProfile
from app.models.test_generation import (
    GeneratedTestFile,
    GenerationSummary,
    TestGenerationResult,
)
from app.models.test_plan import TestPlan, TestSpec


def generate_test_scaffolds(
    plan: TestPlan,
    codemap: CodeMap,
    profile: ProjectProfile,
) -> TestGenerationResult:
    """Generate deterministic test scaffolds from the test plan.

    Args:
        plan: The M4 test plan with prioritised specs.
        codemap: The M3 code map with source signatures.
        profile: The M2 project profile for framework detection.

    Returns:
        TestGenerationResult with generated file contents and metadata.
    """
    warnings = list(plan.warnings)
    framework = _detect_framework(profile)
    source_index = _build_source_index(codemap)

    specs_by_module: dict[str, list[TestSpec]] = {}
    for spec in plan.specs:
        specs_by_module.setdefault(spec.target_file, []).append(spec)

    files: list[GeneratedTestFile] = []
    total_functions = 0
    total_edge_cases = 0
    by_priority: dict[int, int] = {}
    by_type: dict[str, int] = {}
    func_cap_hit = False

    for module_path in sorted(specs_by_module.keys()):
        module_specs = specs_by_module[module_path]
        if func_cap_hit:
            break
        if len(files) >= config.MAX_GENERATED_FILES:
            warnings.append(
                f"Generated file count exceeded {config.MAX_GENERATED_FILES}; truncated."
            )
            break

        content, func_count, edge_count = _render_module(
            module_path, module_specs, source_index, framework
        )

        if total_functions + func_count > config.MAX_GENERATED_FUNCTIONS:
            func_cap_hit = True
            warnings.append(
                f"Generated function count exceeded {config.MAX_GENERATED_FUNCTIONS}; truncated."
            )
            break

        content_bytes = len(content.encode("utf-8"))
        if content_bytes > config.MAX_SCAFFOLD_CONTENT_BYTES:
            warnings.append(
                f"Generated file {module_path} exceeds {config.MAX_SCAFFOLD_CONTENT_BYTES} bytes; truncated."
            )
            encoded = content.encode("utf-8")
            content = encoded[: config.MAX_SCAFFOLD_CONTENT_BYTES].decode("utf-8", errors="ignore")

        priorities = [s.priority for s in module_specs]
        p_min = min(priorities) if priorities else 1
        p_max = max(priorities) if priorities else 5

        test_module_name = "test_" + module_path.rsplit("/", 1)[-1].replace(".py", "")
        file_path = f"{test_module_name}.py"

        files.append(GeneratedTestFile(
            file_path=file_path,
            content=content,
            target_count=len(module_specs),
            priority_range=f"{p_min}-{p_max}" if p_min != p_max else str(p_min),
            framework=framework,
        ))

        total_functions += func_count
        total_edge_cases += edge_count
        for spec in module_specs:
            by_priority[spec.priority] = by_priority.get(spec.priority, 0) + 1
            by_type[spec.test_type] = by_type.get(spec.test_type, 0) + 1

    summary = GenerationSummary(
        total_files=len(files),
        total_test_functions=total_functions,
        total_edge_cases=total_edge_cases,
        by_priority=by_priority,
        by_type=by_type,
        framework_used=framework,
    )

    return TestGenerationResult(
        project_id=plan.project_id,
        created_at=datetime.now(timezone.utc),
        files=files,
        summary=summary,
        warnings=warnings,
    )


def _detect_framework(profile: ProjectProfile) -> str:
    frameworks = profile.tests.frameworks
    if "pytest" in frameworks:
        return "pytest"
    if "unittest" in frameworks:
        return "unittest"
    return "pytest"


def _build_source_index(codemap: CodeMap) -> dict[str, SourceFunction | SourceClass]:
    index: dict[str, SourceFunction | SourceClass] = {}
    for mod in codemap.source_modules:
        for func in mod.functions:
            index[func.qualified_name] = func
        for cls in mod.classes:
            index[cls.qualified_name] = cls
            for method in cls.methods:
                index[method.qualified_name] = method
    return index


def _render_module(
    module_path: str,
    specs: list[TestSpec],
    source_index: dict[str, SourceFunction | SourceClass],
    framework: str,
) -> tuple[str, int, int]:
    module_name = module_path.rsplit("/", 1)[-1].replace(".py", "")
    sorted_specs = sorted(specs, key=lambda s: (s.priority, s.target_qualified_name))

    if framework == "unittest":
        return _render_unittest_module(module_name, sorted_specs, source_index)
    return _render_pytest_module(module_name, sorted_specs, source_index)


def _render_pytest_module(
    module_name: str,
    specs: list[TestSpec],
    source_index: dict[str, SourceFunction | SourceClass],
) -> tuple[str, int, int]:
    lines: list[str] = []
    lines.append(f'"""Tests for {module_name} (auto-generated scaffold).')
    lines.append("")
    lines.append("Generated by AI Test Platform — deterministic test scaffolding.")
    lines.append('"""')
    lines.append("")

    needs_asyncio = any(
        _is_async_target(spec, source_index) for spec in specs
    )
    if needs_asyncio:
        lines.append("import pytest")
        lines.append("")

    func_count = 0
    edge_count = 0

    class_specs = [s for s in specs if s.target_type == "method"]
    func_specs = [s for s in specs if s.target_type != "method"]

    class_groups: dict[str, list[TestSpec]] = {}
    for spec in class_specs:
        class_name = spec.target_qualified_name.rsplit(".", 1)[0]
        class_groups.setdefault(class_name, []).append(spec)

    for spec in func_specs:
        f, e = _render_pytest_function(lines, spec, source_index)
        func_count += f
        edge_count += e

    for class_name in sorted(class_groups.keys()):
        class_spec_list = class_groups[class_name]
        lines.append(f"class Test{class_name}:")
        lines.append(f'    """Tests for {class_name}.')
        lines.append('    """')
        lines.append("")
        lines.append("    def setup_method(self):")
        lines.append('        """Set up test instance."""')
        lines.append("        pass  # TODO: instantiate " + class_name)
        lines.append("")

        for spec in class_spec_list:
            f, e = _render_pytest_method(lines, spec, source_index, indent="    ")
            func_count += f
            edge_count += e

    content = "\n".join(lines) + "\n"
    return content, func_count, edge_count


def _render_pytest_function(
    lines: list[str],
    spec: TestSpec,
    source_index: dict[str, SourceFunction | SourceClass],
    indent: str = "",
) -> tuple[int, int]:
    func_count = 0
    edge_count = 0
    is_async = _is_async_target(spec, source_index)
    source = source_index.get(spec.target_qualified_name)

    if is_async:
        lines.append(f"{indent}@pytest.mark.asyncio")

    lines.append(f"{indent}async def {spec.suggested_test_name}():" if is_async else
                 f"{indent}def {spec.suggested_test_name}():")

    doc = _build_docstring(spec, indent)
    for dl in doc:
        lines.append(dl)

    lines.append(f'{indent}    raise NotImplementedError("Scaffold generated by AI Test Platform")')
    lines.append("")
    func_count += 1

    for ec in spec.edge_cases[:config.MAX_EDGE_CASE_TESTS_PER_TARGET]:
        edge_name = (
            f"test_{spec.target_qualified_name.rsplit('.', 1)[-1]}"
            f"_edge_{ec.parameter}_{ec.case_type}"
        )
        if is_async:
            lines.append(f"{indent}@pytest.mark.asyncio")
        lines.append(f"{indent}async def {edge_name}():" if is_async else
                     f"{indent}def {edge_name}():")
        lines.append(f'{indent}    """Edge case: {ec.description}."""')
        lines.append(f'{indent}    raise NotImplementedError("Edge case: {ec.description}")')
        lines.append("")
        edge_count += 1
        func_count += 1

    return func_count, edge_count


def _render_pytest_method(
    lines: list[str],
    spec: TestSpec,
    source_index: dict[str, SourceFunction | SourceClass],
    indent: str = "    ",
) -> tuple[int, int]:
    func_count = 0
    edge_count = 0
    is_async = _is_async_target(spec, source_index)
    method_name = spec.target_qualified_name.rsplit(".", 1)[-1]

    if is_async:
        lines.append(f"{indent}@pytest.mark.asyncio")

    lines.append(f"{indent}async def {spec.suggested_test_name}(self):" if is_async else
                 f"{indent}def {spec.suggested_test_name}(self):")

    doc = _build_docstring(spec, indent)
    for dl in doc:
        lines.append(dl)

    lines.append(f'{indent}    raise NotImplementedError("Scaffold generated by AI Test Platform")')
    lines.append("")
    func_count += 1

    for ec in spec.edge_cases[:config.MAX_EDGE_CASE_TESTS_PER_TARGET]:
        edge_name = (
            f"test_{method_name}"
            f"_edge_{ec.parameter}_{ec.case_type}"
        )
        if is_async:
            lines.append(f"{indent}@pytest.mark.asyncio")
        lines.append(f"{indent}async def {edge_name}(self):" if is_async else
                     f"{indent}def {edge_name}(self):")
        lines.append(f'{indent}    """Edge case: {ec.description}."""')
        lines.append(f'{indent}    raise NotImplementedError("Edge case: {ec.description}")')
        lines.append("")
        edge_count += 1
        func_count += 1

    return func_count, edge_count


def _render_unittest_module(
    module_name: str,
    specs: list[TestSpec],
    source_index: dict[str, SourceFunction | SourceClass],
) -> tuple[str, int, int]:
    lines: list[str] = []
    lines.append(f'"""Tests for {module_name} (auto-generated scaffold).')
    lines.append("")
    lines.append("Generated by AI Test Platform — deterministic test scaffolding.")
    lines.append('"""')
    lines.append("")
    lines.append("import unittest")
    lines.append("")

    func_count = 0
    edge_count = 0

    func_specs = [s for s in specs if s.target_type != "method"]
    class_specs = [s for s in specs if s.target_type == "method"]

    class_groups: dict[str, list[TestSpec]] = {}
    for spec in class_specs:
        class_name = spec.target_qualified_name.rsplit(".", 1)[0]
        class_groups.setdefault(class_name, []).append(spec)

    if func_specs:
        lines.append(f"class Test{module_name}(unittest.TestCase):")
        lines.append(f'    """Tests for top-level functions in {module_name}."""')
        lines.append("")
        for spec in func_specs:
            f, e = _render_unittest_method(lines, spec, source_index)
            func_count += f
            edge_count += e
        lines.append("")

    for class_name in sorted(class_groups.keys()):
        class_spec_list = class_groups[class_name]
        lines.append(f"class Test{class_name}(unittest.TestCase):")
        lines.append(f'    """Tests for {class_name}."""')
        lines.append("")
        lines.append("    def setUp(self):")
        lines.append('        """Set up test instance."""')
        lines.append("        pass  # TODO: instantiate " + class_name)
        lines.append("")
        for spec in class_spec_list:
            f, e = _render_unittest_method(lines, spec, source_index)
            func_count += f
            edge_count += e
        lines.append("")

    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    unittest.main()")
    lines.append("")

    content = "\n".join(lines) + "\n"
    return content, func_count, edge_count


def _render_unittest_method(
    lines: list[str],
    spec: TestSpec,
    source_index: dict[str, SourceFunction | SourceClass],
    indent: str = "    ",
) -> tuple[int, int]:
    func_count = 0
    edge_count = 0

    lines.append(f"{indent}def {spec.suggested_test_name}(self):")
    doc = _build_docstring(spec, indent)
    for dl in doc:
        lines.append(dl)
    lines.append(f'{indent}    raise NotImplementedError("Scaffold generated by AI Test Platform")')
    lines.append("")
    func_count += 1

    method_name = spec.target_qualified_name.rsplit(".", 1)[-1]
    for ec in spec.edge_cases[:config.MAX_EDGE_CASE_TESTS_PER_TARGET]:
        edge_name = (
            f"test_{method_name}"
            f"_edge_{ec.parameter}_{ec.case_type}"
        )
        lines.append(f"{indent}def {edge_name}(self):")
        lines.append(f'{indent}    """Edge case: {ec.description}."""')
        lines.append(f'{indent}    raise NotImplementedError("Edge case: {ec.description}")')
        lines.append("")
        edge_count += 1
        func_count += 1

    return func_count, edge_count


def _build_docstring(spec: TestSpec, indent: str) -> list[str]:
    lines: list[str] = []
    lines.append(f'{indent}    """{spec.test_type.replace("_", " ").title()} test for '
                 f"{spec.target_qualified_name.rsplit('.', 1)[-1]}.")
    if spec.preconditions:
        lines.append(f"{indent}    ")
        for p in spec.preconditions:
            lines.append(f"{indent}    Preconditions: {p}" if spec.preconditions.index(p) == 0
                         else f"{indent}    {p}")
    lines.append(f'{indent}    """')
    return lines


def _is_async_target(
    spec: TestSpec,
    source_index: dict[str, SourceFunction | SourceClass],
) -> bool:
    source = source_index.get(spec.target_qualified_name)
    if isinstance(source, SourceFunction):
        return source.is_async
    return False



def write_generated_files(
    result: TestGenerationResult,
    workspace,
) -> None:
    """Write generated test files to the workspace."""
    from pathlib import Path
    ws = workspace
    gen_dir = Path(ws) / result.project_id / "generated_tests"
    gen_dir.mkdir(parents=True, exist_ok=True)

    init_path = gen_dir / "__init__.py"
    if not init_path.exists():
        init_path.write_text("", encoding="utf-8")

    for gf in result.files:
        dest = gen_dir / gf.file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(gf.content, encoding="utf-8")
