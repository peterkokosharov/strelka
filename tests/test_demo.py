# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""The phase-1 demo builds and renders headlessly, with menu + status + dialog."""

import importlib.util
import pathlib

from py_tvision.events import Command, key_event
from py_tvision.platform.headless import HeadlessTerminal

DEMO = pathlib.Path(__file__).parent.parent / "examples" / "demo.py"


def _load_demo():
    spec = importlib.util.spec_from_file_location("strelka_demo", DEMO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_app_renders_bands():
    demo = _load_demo()
    app = demo.DemoApp(HeadlessTerminal(70, 22), theme="classic")
    app.redraw()
    snap = app.screen.back.snapshot()
    assert "File" in snap[0] and "Help" in snap[0]
    assert "Exit" in snap[-1]
    assert any("Welcome" in row for row in snap)


def test_demo_dialog_builds_and_runs_modal():
    demo = _load_demo()
    app = demo.DemoApp(HeadlessTerminal(70, 22), theme="modern")
    dlg = demo._make_dialog(app, 56, 20)
    # It has an input seeded "hello", a combo/spinner and OK/Cancel.
    assert dlg.input.data == "hello"
    assert dlg.colour.value == "green"
    assert dlg.count.value == 3
    app.terminal.feed_events(key_event("Esc"))
    assert app.exec_view(dlg) == Command.CANCEL


def test_demo_about_via_command():
    demo = _load_demo()
    app = demo.DemoApp(HeadlessTerminal(70, 22), theme="classic")
    # The About message box is modal; feed an Enter to close it.
    from py_tvision.events import command_event
    app.terminal.feed_events(key_event("Enter"))
    app._dispatch(command_event(demo.CM_ABOUT))
    # It returns without hanging; screen is intact.
    assert app.screen.height == 22
