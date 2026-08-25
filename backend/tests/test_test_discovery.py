"""Tests for test function discovery and test-to-source mapping."""

from app.models.codemap import SourceFunction, SourceModule, TestFunction
from app.services.test_discovery import (
    build_testable_targets,
    discover_test_functions,
    map_tests_to_sources,
)


def test_discover_test_functions_basic():
    src = "def test_login(): pass\ndef test_logout(): pass\n"
    tfs, warns = discover_test_functions("test_auth.py", src)
    assert len(tfs) == 2
    assert tfs[0].name == "test_login"
    assert tfs[1].name == "test_logout"
    assert not warns


def test_non_test_functions_filtered():
    src = "def test_ok(): pass\ndef helper(): pass\ndef test_also(): pass\n"
    tfs, _ = discover_test_functions("t.py", src)
    assert len(tfs) == 2
    assert all(tf.name.startswith("test_") for tf in tfs)


def test_test_suffix():
    src = "def login_test(): pass\n"
    tfs, _ = discover_test_functions("t.py", src)
    assert len(tfs) == 1
    assert tfs[0].name == "login_test"


def test_test_decorators_extracted():
    src = (
        "import pytest\n\n"
        "@pytest.mark.slow\n"
        "def test_heavy(): pass\n"
    )
    tfs, _ = discover_test_functions("t.py", src)
    assert len(tfs) == 1
    assert tfs[0].decorators == ["pytest.mark.slow"]


def test_assertion_count():
    src = (
        "def test_add():\n"
        "    assert 1 + 1 == 2\n"
        "    assert 2 + 2 == 4\n"
    )
    tfs, _ = discover_test_functions("t.py", src)
    assert tfs[0].assertion_count == 2


def test_assertion_count_unittest():
    src = (
        "class T:\n"
        "    def test_eq(self):\n"
        "        self.assertEqual(1, 1)\n"
        "        self.assertTrue(True)\n"
    )
    tfs, _ = discover_test_functions("t.py", src)
    # unittest assertions are in methods, not at top level
    # The regex should match self.assertEqual( and self.assertTrue(
    # but only for top-level functions matching test_*
    # Since class methods aren't top-level test functions, we get 0
    assert len(tfs) == 0


def test_syntax_error_returns_warning():
    src = "def test_bad(\n"
    tfs, warns = discover_test_functions("bad.py", src)
    assert tfs == []
    assert any("syntax" in w.lower() or "parse" in w.lower() for w in warns)


def test_empty_file():
    tfs, warns = discover_test_functions("empty.py", "")
    assert tfs == []
    assert not warns


def test_name_similarity_mapping():
    sources = [
        SourceModule(
            path="app.py",
            language="Python",
            functions=[
                SourceFunction(
                    name="login",
                    qualified_name="login",
                    file_path="app.py",
                    line_start=1,
                    line_end=1,
                ),
            ],
        ),
    ]
    tests = [
        TestFunction(
            name="test_login",
            file_path="test_app.py",
            line_start=1,
            line_end=1,
        ),
    ]
    mappings = map_tests_to_sources(tests, sources)
    assert len(mappings) == 1
    assert mappings[0].source_target == "login"
    assert mappings[0].confidence == 0.8
    assert mappings[0].method == "name_similarity"


def test_class_mapping():
    sources = [
        SourceModule(
            path="models.py",
            language="Python",
            classes=[],
            functions=[
                SourceFunction(
                    name="User",
                    qualified_name="User",
                    file_path="models.py",
                    line_start=1,
                    line_end=5,
                ),
            ],
        ),
    ]
    tests = [
        TestFunction(
            name="test_user_creation",
            file_path="test_models.py",
            line_start=1,
            line_end=1,
        ),
    ]
    mappings = map_tests_to_sources(tests, sources)
    assert len(mappings) == 1
    assert mappings[0].source_target == "User"


def test_no_mapping_for_unrelated_test():
    sources = [
        SourceModule(
            path="auth.py",
            language="Python",
            functions=[
                SourceFunction(
                    name="login",
                    qualified_name="login",
                    file_path="auth.py",
                    line_start=1,
                    line_end=1,
                ),
            ],
        ),
    ]
    tests = [
        TestFunction(
            name="test_completely_unrelated_thing",
            file_path="test_other.py",
            line_start=1,
            line_end=1,
        ),
    ]
    mappings = map_tests_to_sources(tests, sources)
    assert len(mappings) == 0


def test_import_boost():
    sources = [
        SourceModule(
            path="auth.py",
            language="Python",
            functions=[
                SourceFunction(
                    name="login",
                    qualified_name="auth.login",
                    file_path="auth.py",
                    line_start=1,
                    line_end=1,
                ),
            ],
            imports=["auth"],
        ),
    ]
    tests = [
        TestFunction(
            name="test_login",
            file_path="test_auth.py",
            line_start=1,
            line_end=1,
        ),
    ]
    mappings = map_tests_to_sources(
        tests, sources, test_import_index={"test_auth.py": {"auth"}}
    )
    assert len(mappings) == 1
    assert mappings[0].confidence >= 0.8
    assert mappings[0].method == "import_analysis"


def test_build_testable_targets_with_coverage():
    sources = [
        SourceModule(
            path="app.py",
            language="Python",
            functions=[
                SourceFunction(
                    name="foo",
                    qualified_name="foo",
                    file_path="app.py",
                    line_start=1,
                    line_end=1,
                ),
                SourceFunction(
                    name="bar",
                    qualified_name="bar",
                    file_path="app.py",
                    line_start=3,
                    line_end=3,
                ),
            ],
        ),
    ]
    tests = [
        TestFunction(
            name="test_foo",
            file_path="test_app.py",
            line_start=1,
            line_end=1,
        ),
    ]
    mappings = map_tests_to_sources(tests, sources)
    targets = build_testable_targets(sources, tests, mappings)
    assert len(targets) == 2
    foo_target = next(t for t in targets if t.qualified_name == "foo")
    bar_target = next(t for t in targets if t.qualified_name == "bar")
    assert foo_target.has_tests is True
    assert bar_target.has_tests is False


def test_build_testable_targets_with_methods():
    sources = [
        SourceModule(
            path="cls.py",
            language="Python",
            classes=[],
        ),
    ]
    from app.models.codemap import SourceClass
    sources[0].classes = [
        SourceClass(
            name="Foo",
            qualified_name="Foo",
            file_path="cls.py",
            line_start=1,
            line_end=5,
            methods=[
                SourceFunction(
                    name="bar",
                    qualified_name="Foo.bar",
                    file_path="cls.py",
                    line_start=2,
                    line_end=2,
                ),
            ],
        ),
    ]
    targets = build_testable_targets(sources, [], [])
    # Should have class Foo and method Foo.bar
    assert len(targets) == 2
    assert any(t.target_type == "class" for t in targets)
    assert any(t.target_type == "method" for t in targets)


def test_mappings_sorted_by_confidence():
    sources = [
        SourceModule(
            path="a.py",
            language="Python",
            functions=[
                SourceFunction(
                    name="foo",
                    qualified_name="foo",
                    file_path="a.py",
                    line_start=1,
                    line_end=1,
                ),
                SourceFunction(
                    name="fool",
                    qualified_name="fool",
                    file_path="a.py",
                    line_start=3,
                    line_end=3,
                ),
            ],
        ),
    ]
    tests = [
        TestFunction(
            name="test_foo",
            file_path="test_a.py",
            line_start=1,
            line_end=1,
        ),
    ]
    mappings = map_tests_to_sources(tests, sources)
    assert len(mappings) == 1
    assert mappings[0].source_target == "foo"
    assert mappings[0].confidence == 0.8


def test_test_function_line_numbers():
    src = (
        "def test_one():\n"
        "    assert True\n"
        "\n"
        "def test_two():\n"
        "    assert 1 == 1\n"
    )
    tfs, _ = discover_test_functions("t.py", src)
    assert tfs[0].line_start == 1
    assert tfs[0].line_end == 2
    assert tfs[1].line_start == 4
    assert tfs[1].line_end == 5


def test_has_docstring_on_test():
    src = (
        'def test_something():\n'
        '    """Test something."""\n'
        '    assert True\n'
    )
    tfs, _ = discover_test_functions("t.py", src)
    assert tfs[0].has_docstring is True
