"""Lightweight AST-based function-level call graph builder.

Scans Python source files to extract caller → callee relationships at the
function/method level. Deterministic, read-only, no code execution.

Limitations (documented, accepted):
- Only resolves calls within the project's Python files.
- Name matching is best-effort: does not resolve imports, qualified
  names, or cross-module references. A call to `foo()` is matched
  against any function named `foo` in the same or any other module.
- Class method calls via `self.method()` are matched against method
  names across all classes.
"""

import ast
from collections import defaultdict


class CallGraph:
    """Immutable adjacency list of function-level caller/callee relationships."""

    def __init__(self) -> None:
        self._adjacency: dict[str, set[str]] = defaultdict(set)
        self._known_targets: set[str] = set()
        # bare_name → first registered qualified_name (for self.method() resolution)
        self._bare_to_qn: dict[str, str] = {}

    def add_call(self, caller: str, callee: str) -> None:
        self._adjacency[caller].add(callee)

    def add_target(self, qualified_name: str) -> None:
        self._known_targets.add(qualified_name)
        bare = qualified_name.rsplit(".", 1)[-1]
        if bare not in self._bare_to_qn:
            self._bare_to_qn[bare] = qualified_name

    def _resolve(self, name: str) -> set[str]:
        """Resolve a raw callee name to matching known target qualified names."""
        if name in self._known_targets:
            return {name}
        qn = self._bare_to_qn.get(name)
        if qn and qn in self._known_targets:
            return {qn}
        return set()

    def callees_of(self, caller: str) -> set[str]:
        raw = self._adjacency.get(caller, set())
        result: set[str] = set()
        for name in raw:
            result |= self._resolve(name)
        return result

    def callers_of(self, callee: str) -> set[str]:
        resolved = self._resolve(callee)
        return {
            caller
            for caller, callees in self._adjacency.items()
            if callees & resolved
        }

    def fan_in(self, callee: str) -> int:
        return len(self.callers_of(callee))

    @property
    def known_targets(self) -> set[str]:
        return set(self._known_targets)

    @property
    def edges(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for caller, callees in self._adjacency.items():
            resolved: set[str] = set()
            for name in callees:
                resolved |= self._resolve(name)
            if resolved:
                result[caller] = resolved
        return result


def build_call_graph(
    source_files: list[tuple[str, str]],
) -> CallGraph:
    """Build a function-level call graph from Python source files.

    Args:
        source_files: list of (relative_path, file_content) pairs.

    Returns:
        CallGraph with known targets and resolved edges.
    """
    graph = CallGraph()

    # First pass: parse every file, register targets, collect call info
    # file_path → list[(caller_qn, callee_name)]
    pending_calls: dict[str, list[tuple[str, str]]] = defaultdict(list)
    # AST node id → qualified name (for resolving which function a call belongs to)
    node_qn: dict[int, str] = {}

    for path, content in source_files:
        tree = _safe_parse(path, content)
        if tree is None:
            continue

        # Register all function/method targets in this file
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qn = _qualify(node, tree, path)
                graph.add_target(qn)
                node_qn[id(node)] = qn

        # Collect calls within function bodies
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller_qn = node_qn.get(id(node), node.name)
                for call_node in _iter_calls(node):
                    callee_name = _extract_call_name(call_node)
                    if callee_name:
                        pending_calls[path].append((caller_qn, callee_name))

    # Second pass: wire up edges
    for path, calls in pending_calls.items():
        for caller_qn, callee_name in calls:
            graph.add_call(caller_qn, callee_name)

    return graph


def _safe_parse(path: str, content: str) -> ast.Module | None:
    try:
        return ast.parse(content)
    except SyntaxError:
        return None


def _qualify(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    tree: ast.Module,
    file_path: str,
) -> str:
    """Determine the qualified name for a function node.

    If the function is a method inside a class, returns 'ClassName.method_name'.
    Otherwise returns just 'function_name'.
    """
    for cls_node in ast.walk(tree):
        if isinstance(cls_node, ast.ClassDef):
            for item in cls_node.body:
                if item is func_node:
                    return f"{cls_node.name}.{func_node.name}"
    return func_node.name


def _iter_calls(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Call]:
    return [n for n in ast.walk(func_node) if isinstance(n, ast.Call)]


def _extract_call_name(call_node: ast.Call) -> str | None:
    """Extract the bare function name from a Call node.

    Handles: foo(), obj.method(), module.func(), cls.method().
    Returns the last attribute name (best-effort matching against known targets).
    """
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
