"""Tests for the Python ast-based source code analyzer."""

from app.services.code_analyzer import analyze_source_file


def test_extract_top_level_functions():
    src = (
        "def hello(): pass\n"
        "def greet(name): pass\n"
    )
    mod, warns = analyze_source_file("app.py", src)
    assert len(mod.functions) == 2
    assert mod.functions[0].name == "hello"
    assert mod.functions[1].name == "greet"
    assert mod.functions[1].args == ["name"]
    assert not warns


def test_extract_class_with_methods():
    src = (
        "class Foo:\n"
        "    def bar(self): pass\n"
        "    def baz(self, x): pass\n"
    )
    mod, warns = analyze_source_file("models.py", src)
    assert len(mod.classes) == 1
    cls = mod.classes[0]
    assert cls.name == "Foo"
    assert cls.qualified_name == "Foo"
    assert len(cls.methods) == 2
    assert cls.methods[0].qualified_name == "Foo.bar"
    assert cls.methods[1].qualified_name == "Foo.baz"
    assert cls.methods[1].args == ["self", "x"]


def test_async_function_detected():
    src = "async def fetch(): pass\n"
    mod, _ = analyze_source_file("net.py", src)
    assert len(mod.functions) == 1
    assert mod.functions[0].is_async is True


def test_async_method_detected():
    src = (
        "class Api:\n"
        "    async def call(self): pass\n"
    )
    mod, _ = analyze_source_file("api.py", src)
    assert mod.classes[0].methods[0].is_async is True


def test_decorators_extracted():
    src = (
        "@staticmethod\n"
        "def util(): pass\n\n"
        "@app.get('/health')\n"
        "def health(): pass\n"
    )
    mod, _ = analyze_source_file("app.py", src)
    assert mod.functions[0].decorators == ["staticmethod"]
    assert mod.functions[1].decorators == ["app.get"]


def test_class_decorators_extracted():
    src = (
        "@dataclass\n"
        "class Config:\n"
        "    pass\n"
    )
    mod, _ = analyze_source_file("cfg.py", src)
    assert mod.classes[0].decorators == ["dataclass"]


def test_has_docstring_true():
    src = (
        'def hello():\n'
        '    """Say hello."""\n'
        '    pass\n'
    )
    mod, _ = analyze_source_file("doc.py", src)
    assert mod.functions[0].has_docstring is True


def test_has_docstring_false():
    src = "def hello(): pass\n"
    mod, _ = analyze_source_file("nodoc.py", src)
    assert mod.functions[0].has_docstring is False


def test_class_has_docstring():
    src = (
        'class Foo:\n'
        '    """A foo class."""\n'
        '    pass\n'
    )
    mod, _ = analyze_source_file("cls.py", src)
    assert mod.classes[0].has_docstring is True


def test_empty_file():
    mod, warns = analyze_source_file("empty.py", "")
    assert mod.functions == []
    assert mod.classes == []
    assert not warns


def test_syntax_error_handled():
    mod, warns = analyze_source_file("bad.py", "def foo(\n  indent")
    assert mod.functions == []
    assert mod.classes == []
    assert len(warns) == 1
    assert "parse" in warns[0].lower()


def test_imports_extracted():
    src = (
        "import os\n"
        "import json\n"
        "from pathlib import Path\n"
    )
    mod, _ = analyze_source_file("imports.py", src)
    assert "os" in mod.imports
    assert "json" in mod.imports
    assert "pathlib" in mod.imports


def test_line_numbers_correct():
    src = (
        "def a():\n"       # line 1
        "    pass\n"        # line 2
        "\n"                 # line 3
        "def b():\n"        # line 4
        "    pass\n"        # line 5
    )
    mod, _ = analyze_source_file("lines.py", src)
    assert mod.functions[0].line_start == 1
    assert mod.functions[0].line_end == 2
    assert mod.functions[1].line_start == 4
    assert mod.functions[1].line_end == 5


def test_method_line_numbers():
    src = (
        "class Foo:\n"       # line 1
        "    def bar(self):\n"  # line 2
        "        pass\n"     # line 3
    )
    mod, _ = analyze_source_file("mlines.py", src)
    assert mod.classes[0].line_start == 1
    assert mod.classes[0].line_end == 3
    assert mod.classes[0].methods[0].line_start == 2
    assert mod.classes[0].methods[0].line_end == 3


def test_args_various():
    src = (
        "def f(a, b=1, *args, c, **kwargs): pass\n"
    )
    mod, _ = analyze_source_file("args.py", src)
    assert mod.functions[0].args == ["a", "b", "*args", "c", "**kwargs"]


def test_class_bases():
    src = (
        "class Derived(Base):\n"
        "    pass\n"
    )
    mod, _ = analyze_source_file("base.py", src)
    assert mod.classes[0].bases == ["Base"]


def test_nested_functions_not_top_level():
    src = (
        "def outer():\n"
        "    def inner(): pass\n"
    )
    mod, _ = analyze_source_file("nested.py", src)
    assert len(mod.functions) == 1
    assert mod.functions[0].name == "outer"
