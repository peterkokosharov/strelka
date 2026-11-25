# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Application loop: modal exec_view, resize, idle/timers, threaded post."""

import threading
import time

from py_tvision.app import Program
from py_tvision.events import Command, key_event
from py_tvision.geometry import Rect
from py_tvision.platform.headless import HeadlessTerminal
from py_tvision.views import State
from py_tvision.widgets import Button, InputLine, Label, StatusItem, StatusLine
from py_tvision.widgets.menu import MenuBar, MenuItem, SubMenu
from py_tvision.window import Dialog


def build_app(w=60, h=20):
    prog = Program(HeadlessTerminal(w, h), theme="classic")
    bar = MenuBar(Rect(0, 0, w, 1), [SubMenu("~F~ile", [MenuItem("E~x~it", Command.QUIT)])])
    prog.set_menu_bar(bar)
    sl = StatusLine(Rect(0, h - 1, w, h), [StatusItem("~Alt-X~ Exit", "Alt+X", Command.QUIT)])
    prog.set_status_line(sl)
    return prog


def ok_dialog(prog):
    w, h = prog.screen.width, prog.screen.height
    dlg = Dialog(Rect(5, 3, w - 5, h - 4), "Dialog")
    inp = InputLine(Rect(10, 2, 30, 3), text="hi")
    dlg.insert(inp)
    dlg.insert(Label(Rect(2, 2, 9, 3), "~N~ame:", inp))
    dlg.insert(Button(Rect(2, 6, 12, 7), "O~K~", Command.OK, default=True))
    dlg.insert(Button(Rect(14, 6, 24, 7), "~C~ancel", Command.CANCEL))
    return dlg


def test_exec_view_returns_ok_on_enter():
    prog = build_app()
    dlg = ok_dialog(prog)
    # The OK button is the first selectable; Enter fires it.
    prog.terminal.feed_events(key_event("Enter"))
    result = prog.exec_view(dlg)
    assert result == Command.OK
    assert dlg.owner is None  # removed after modal


def test_exec_view_returns_cancel_on_esc():
    prog = build_app()
    dlg = ok_dialog(prog)
    prog.terminal.feed_events(key_event("Esc"))
    assert prog.exec_view(dlg) == Command.CANCEL


def test_exec_view_cancel_via_button():
    prog = build_app()
    dlg = ok_dialog(prog)
    # Alt+C hits the Cancel button (pre-process) regardless of focus.
    from py_tvision.events import Mod
    prog.terminal.feed_events(key_event("C", Mod.ALT))
    assert prog.exec_view(dlg) == Command.CANCEL


def test_resize_keeps_status_line_at_bottom():
    prog = build_app(60, 20)
    prog.resize(100, 30)
    assert prog.bounds.width == 100 and prog.bounds.height == 30
    assert prog.menubar.bounds.width == 100
    sl = prog.status_line
    assert sl.bounds.y1 == 29 and sl.bounds.y2 == 30
    assert sl.bounds.width == 100
    assert prog.desktop.bounds.height == 28  # between bar and status line


def test_timer_fires_on_idle():
    prog = build_app()
    ticks = []
    prog.every(0.0, lambda: ticks.append(1))
    prog.pump(0.0)  # empty batch -> idle -> timer
    assert ticks


def test_threaded_post_runs_on_pump():
    prog = build_app()
    result = []

    def worker():
        prog.post(lambda: result.append("done"))

    t = threading.Thread(target=worker)
    t.start(); t.join()
    # Give the queue a turn.
    prog.pump(0.0)
    assert result == ["done"]
    assert prog.terminal.woken >= 1  # wake() called from post


def test_cursor_follows_focused_input():
    prog = build_app()
    dlg = ok_dialog(prog)
    prog.desktop.insert(dlg)
    prog.desktop.focus_child(dlg)
    dlg.set_state(State.FOCUSED, True)
    inp = next(c for c in dlg.children if isinstance(c, InputLine))
    inp.focus()
    prog.redraw()
    assert prog.screen.cursor is not None
    io = inp.abs_origin()
    assert prog.screen.cursor.y == io.y


def test_full_screen_snapshot_has_all_bands():
    prog = build_app(50, 12)
    prog.redraw()
    snap = prog.screen.back.snapshot()
    assert "File" in snap[0]  # menu bar on top
    assert "Exit" in snap[-1]  # status line at bottom
    # desktop backdrop between them
    assert "░" in "".join(snap[1:-1])
