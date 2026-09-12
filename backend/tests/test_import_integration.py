"""Regression tests for import-path resolution in the sandbox source copy.

Improvement derives module names by sanitising every path component
(``m11-demo/calc.py`` -> ``m11_demo.calc``); CPython does not translate
hyphenated directory/file names, so the sandbox source must carry mirrored
module-safe aliases. These tests exercise ``_mirror_module_names`` and host
level imports (Docker is unavailable in CI; the mirror is host-agnostic).
"""

import sys
from pathlib import Path

import pytest

from app.execution.runner import _mirror_module_names


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _importable(root: Path, modname: str):
    root = str(root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        top = modname.split(".")[0]
        for name in [n for n in list(sys.modules) if n == top or n.startswith(top + ".")]:
            del sys.modules[name]
        return __import__(modname, fromlist=["*"])
    finally:
        if root in sys.path:
            sys.path.remove(root)


def test_top_level_module_unaffected(tmp_path):
    root = _tree(tmp_path, {"calc.py": "def add(a, b):\n    return a + b\n"})
    _mirror_module_names(root)
    assert (root / "calc.py").is_file()
    mod = _importable(root, "calc")
    assert mod.add(1, 2) == 3


def test_hyphenated_directory_mirrored(tmp_path):
    root = _tree(tmp_path, {"m11-demo/calc.py": "def add(a, b):\n    return a + b\n"})
    _mirror_module_names(root)
    # Generated test imports `from m11_demo.calc import add`; the twin must exist.
    assert (root / "m11_demo" / "calc.py").is_file()
    mod = _importable(root, "m11_demo.calc")
    assert mod.add(2, 3) == 5


def test_package_with_init(tmp_path):
    root = _tree(tmp_path, {
        "m11_demo/__init__.py": "",
        "m11_demo/calc.py": "def mul(a, b):\n    return a * b\n",
    })
    _mirror_module_names(root)
    mod = _importable(root, "m11_demo.calc")
    assert mod.mul(3, 4) == 12


def test_nested_hyphenated_directories(tmp_path):
    root = _tree(tmp_path, {
        "m11-demo/sub-dir/deep.py": "def sub(a, b):\n    return a - b\n",
    })
    _mirror_module_names(root)
    assert (root / "m11_demo" / "sub_dir" / "deep.py").is_file()
    mod = _importable(root, "m11_demo.sub_dir.deep")
    assert mod.sub(10, 4) == 6


def test_hyphenated_filename_mirrored(tmp_path):
    root = _tree(tmp_path, {
        "pkg/my-mod.py": "def neg(a):\n    return -a\n",
    })
    _mirror_module_names(root)
    assert (root / "pkg" / "my_mod.py").is_file()
    mod = _importable(root, "pkg.my_mod")
    assert mod.neg(7) == -7


def test_leading_digit_directory(tmp_path):
    root = _tree(tmp_path, {"1st-pkg/calc.py": "def one():\n    return 1\n"})
    _mirror_module_names(root)
    # _module_from_path prefixes an underscore for digit-leading components.
    assert (root / "_1st_pkg" / "calc.py").is_file()
    mod = _importable(root, "_1st_pkg.calc")
    assert mod.one() == 1


def test_collision_keeps_first_and_never_overwrites(tmp_path):
    root = _tree(tmp_path, {
        "m11_demo/calc.py": "def which():\n    return 'original'\n",
        "m11-demo/calc.py": "def which():\n    return 'dup'\n",
    })
    before = (root / "m11_demo" / "calc.py").read_text(encoding="utf-8")
    _mirror_module_names(root)
    assert (root / "m11_demo" / "calc.py").read_text(encoding="utf-8") == before
    mod = _importable(root, "m11_demo.calc")
    assert mod.which() == "original"


def test_mirror_skips_unchanged_names(tmp_path):
    root = _tree(tmp_path, {"clean/calc.py": "x = 1\n"})
    files_before = {p.relative_to(root).as_posix() for p in root.rglob("*")}
    _mirror_module_names(root)
    files_after = {p.relative_to(root).as_posix() for p in root.rglob("*")}
    assert files_after == files_before