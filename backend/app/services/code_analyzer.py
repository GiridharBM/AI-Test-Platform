"""Python ast-based source file analysis.

Extracts per-file metadata: functions, classes, methods, signatures,
decorators, docstrings, and imports. Read-only, no code execution.

This module handles ONLY Python files (.py). Other languages are
deferred to Tree-sitter integration in a future milestone.
"""

import ast
import re
from pathlib import Path

from app.models.codemap import SourceClass, SourceFunction, SourceModule


def _has_docstring(node: ast.AST) -> bool:
    return ast.get_docstring(node) is not None


def _extract_decorator(dec_node: ast.expr) -> str:
    """Convert an ast decorator node to a string representation."""
    if isinstance(dec_node, ast.Name):
        return dec_node.id
    if isinstance(dec_node, ast.Attribute):
        parts = []
        node: ast.expr = dec_node
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))
    if isinstance(dec_node, ast.Call):
        return _extract_decorator(dec_node.func)
    return ast.dump(dec_node)


def _extract_args(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract argument names from a function definition node."""
    args: list[str] = []
    a = func_node.args
    for arg in a.posonlyargs:
        args.append(arg.arg)
    for arg in a.args:
        args.append(arg.arg)
    if a.vararg:
        args.append(f"*{a.vararg.arg}")
    for arg in a.kwonlyargs:
        args.append(arg.arg)
    if a.kwarg:
        args.append(f"**{a.kwarg.arg}")
    return args


def _extract_imports(tree: ast.Module) -> list[str]:
    """Extract imported module names from an ast tree."""
    imports: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def analyze_source_file(
    path: str,
    content: str,
) -> tuple[SourceModule, list[str]]:
    """Parse a Python source file and extract its structural metadata.

    Returns (SourceModule, warnings).
    """
    warnings: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        warnings.append(f"Python file could not be parsed: {path} ({exc})")
        return SourceModule(path=path, language="Python"), warnings

    functions: list[SourceFunction] = []
    classes: list[SourceClass] = []
    imports = _extract_imports(tree)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(SourceFunction(
                name=node.name,
                qualified_name=node.name,
                file_path=path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                args=_extract_args(node),
                decorators=[_extract_decorator(d) for d in node.decorator_list],
                has_docstring=_has_docstring(node),
                is_async=isinstance(node, ast.AsyncFunctionDef),
            ))
        elif isinstance(node, ast.ClassDef):
            methods: list[SourceFunction] = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(SourceFunction(
                        name=item.name,
                        qualified_name=f"{node.name}.{item.name}",
                        file_path=path,
                        line_start=item.lineno,
                        line_end=item.end_lineno or item.lineno,
                        args=_extract_args(item),
                        decorators=[_extract_decorator(d) for d in item.decorator_list],
                        has_docstring=_has_docstring(item),
                        is_async=isinstance(item, ast.AsyncFunctionDef),
                    ))
            bases: list[str] = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    parts: list[str] = []
                    n: ast.expr = base
                    while isinstance(n, ast.Attribute):
                        parts.append(n.attr)
                        n = n.value
                    if isinstance(n, ast.Name):
                        parts.append(n.id)
                    bases.append(".".join(reversed(parts)))
            classes.append(SourceClass(
                name=node.name,
                qualified_name=node.name,
                file_path=path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                bases=bases,
                decorators=[_extract_decorator(d) for d in node.decorator_list],
                has_docstring=_has_docstring(node),
                methods=methods,
            ))

    return SourceModule(
        path=path,
        language="Python",
        functions=functions,
        classes=classes,
        imports=imports,
    ), warnings
