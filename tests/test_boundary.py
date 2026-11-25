# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Enforce the UI / logic layer boundary.

The py_tvision toolkit (layer 2) must not depend on the Strelka functional core
(layer 1) or on any adapter. This keeps "one core, many faces" possible: a
future ACP adapter sits on the core beside the TUI without either leaking.
"""

import ast
import pathlib

PKG = pathlib.Path(__file__).parent.parent / "src" / "py_tvision"


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_py_tvision_does_not_import_strelka():
    offenders = {}
    for path in PKG.rglob("*.py"):
        bad = {m for m in _imports(path) if m == "strelka" or m.startswith("strelka.")}
        if bad:
            offenders[str(path)] = bad
    assert not offenders, f"py_tvision must not import the Strelka core: {offenders}"


def test_py_tvision_runtime_is_stdlib_only():
    third_party = {
        "pydantic", "pydantic_settings", "tomli_w", "textual", "rich",
        "psutil", "playwright", "pygments", "markdown_it", "cssutils",
    }
    offenders = {}
    for path in PKG.rglob("*.py"):
        bad = {m.split(".")[0] for m in _imports(path)} & third_party
        if bad:
            offenders[str(path)] = bad
    assert not offenders, f"runtime must be stdlib only: {offenders}"
