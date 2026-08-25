"""Tests for the lightweight AST-based call graph builder."""

from app.services.call_graph import CallGraph, build_call_graph


def test_simple_function_call():
    source = [
        ("a.py", "def foo(): pass\ndef bar(): foo()\n"),
    ]
    graph = build_call_graph(source)
    assert "foo" in graph.known_targets
    assert "bar" in graph.known_targets
    assert "foo" in graph.callees_of("bar")


def test_no_calls():
    source = [
        ("a.py", "def foo(): pass\ndef bar(): pass\n"),
    ]
    graph = build_call_graph(source)
    assert graph.callees_of("foo") == set()
    assert graph.callees_of("bar") == set()


def test_method_calls():
    source = [
        ("a.py", (
            "class MyClass:\n"
            "    def helper(self): pass\n"
            "    def run(self): self.helper()\n"
        )),
    ]
    graph = build_call_graph(source)
    assert "MyClass.run" in graph.known_targets
    assert "MyClass.helper" in graph.known_targets
    assert "MyClass.helper" in graph.callees_of("MyClass.run")


def test_fan_in():
    source = [
        ("a.py", (
            "def shared(): pass\n"
            "def a(): shared()\n"
            "def b(): shared()\n"
            "def c(): shared()\n"
        )),
    ]
    graph = build_call_graph(source)
    assert graph.fan_in("shared") == 3


def test_cross_file_calls():
    source = [
        ("a.py", "def foo(): pass\n"),
        ("b.py", "def bar(): foo()\n"),
    ]
    graph = build_call_graph(source)
    assert "foo" in graph.callees_of("bar")


def test_syntax_error_file_skipped():
    source = [
        ("good.py", "def foo(): pass\n"),
        ("bad.py", "def foo(\n  indent"),
    ]
    graph = build_call_graph(source)
    assert "foo" in graph.known_targets  # from good.py


def test_unknown_callee_not_in_callees():
    """Calls to external/unknown functions should not appear in callees."""
    source = [
        ("a.py", "def foo(): print('hi')\n"),
    ]
    graph = build_call_graph(source)
    assert "print" not in graph.callees_of("foo")


def test_empty_source():
    graph = build_call_graph([])
    assert graph.known_targets == set()


def test_class_with_external_method_call():
    source = [
        ("a.py", (
            "class Foo:\n"
            "    def bar(self): pass\n"
            "class Baz:\n"
            "    def qux(self): pass\n"
            "    def run(self): self.qux()\n"
        )),
    ]
    graph = build_call_graph(source)
    assert "Baz.qux" in graph.callees_of("Baz.run")
    assert "Foo.bar" not in graph.callees_of("Baz.run")


def test_chained_calls():
    source = [
        ("a.py", (
            "def low(): pass\n"
            "def mid(): low()\n"
            "def high(): mid()\n"
        )),
    ]
    graph = build_call_graph(source)
    assert "low" not in graph.callees_of("high")
    assert "mid" in graph.callees_of("high")


def test_edges_property():
    source = [
        ("a.py", "def foo(): pass\ndef bar(): foo()\n"),
    ]
    graph = build_call_graph(source)
    edges = graph.edges
    assert "bar" in edges
    assert "foo" in edges["bar"]


def test_callers_of():
    source = [
        ("a.py", (
            "def shared(): pass\n"
            "def a(): shared()\n"
            "def b(): shared()\n"
        )),
    ]
    graph = build_call_graph(source)
    callers = graph.callers_of("shared")
    assert "a" in callers
    assert "b" in callers
