# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Widget behaviour and drawing (snapshotted into the screen buffer)."""

from py_tvision.app import Program
from py_tvision.events import (
    Command,
    EventKind,
    Mod,
    key_event,
    mouse_event,
    paste_event,
)
from py_tvision.geometry import Rect
from py_tvision.platform.headless import HeadlessTerminal
from py_tvision.views import State
from py_tvision.widgets import (
    Button,
    InputLine,
    Label,
    ListBox,
    MenuBar,
    MenuItem,
    ScrollBar,
    StatusItem,
    StatusLine,
    SubMenu,
)
from py_tvision.widgets.msgbox import OK_CANCEL, build_message_box
from py_tvision.window import Dialog, Window


def new_prog(w=60, h=20):
    return Program(HeadlessTerminal(w, h), theme="classic")


def drain_commands(prog):
    return [e.command for e in prog.post_queue.drain()
            if getattr(e, "kind", None) in (EventKind.COMMAND, EventKind.BROADCAST)]


# --- Button ---------------------------------------------------------------

def test_button_label_and_hotkey_parsed():
    b = Button(Rect(0, 0, 10, 1), "O~K~", Command.OK, default=True)
    assert b.display == "OK"
    assert b.hotkey == "K"


def test_button_enter_when_focused_emits_command():
    prog = new_prog()
    dlg = Dialog(Rect(2, 2, 30, 10), "D")
    btn = Button(Rect(2, 6, 12, 7), "O~K~", Command.OK, default=True)
    dlg.insert(btn)
    prog.desktop.insert(dlg)
    prog.desktop.focus_child(dlg)
    dlg.set_state(State.FOCUSED, True)
    btn.focus()
    ev = key_event("Enter")
    btn.handle_event(ev)
    assert ev.handled
    assert Command.OK in drain_commands(prog)


def test_button_alt_hotkey_emits_without_focus():
    prog = new_prog()
    dlg = Dialog(Rect(2, 2, 30, 10), "D")
    btn = Button(Rect(2, 6, 12, 7), "~C~ancel", Command.CANCEL)
    dlg.insert(btn)
    prog.desktop.insert(dlg)
    ev = key_event("C", Mod.ALT)
    btn.handle_event(ev)
    assert ev.handled
    assert Command.CANCEL in drain_commands(prog)


def test_button_mouse_click_emits():
    prog = new_prog()
    dlg = Dialog(Rect(0, 0, 30, 10), "D")
    btn = Button(Rect(2, 5, 12, 6), "O~K~", Command.OK)
    dlg.insert(btn)
    prog.desktop.insert(dlg)
    o = btn.abs_origin()
    ev = mouse_event(EventKind.MOUSE_DOWN, o.x + 1, o.y)
    btn.handle_event(ev)
    assert Command.OK in drain_commands(prog)


# --- Label ----------------------------------------------------------------

def test_label_hotkey_focuses_link():
    prog = new_prog()
    dlg = Dialog(Rect(0, 0, 40, 10), "D")
    inp = InputLine(Rect(10, 2, 30, 3))
    label = Label(Rect(2, 2, 9, 3), "~N~ame:", inp)
    dlg.insert(inp)
    dlg.insert(label)
    prog.desktop.insert(dlg)
    prog.desktop.focus_child(dlg)
    dlg.set_state(State.FOCUSED, True)
    # Alt+N should move focus to the input line.
    ev = key_event("N", Mod.ALT)
    label.handle_event(ev)
    assert ev.handled
    assert dlg.current is inp


# --- InputLine ------------------------------------------------------------

def test_input_insert_and_backspace():
    inp = InputLine(Rect(0, 0, 20, 1))
    for ch in "abc":
        inp.handle_event(key_event(ch.upper(), text=ch))
    assert inp.data == "abc"
    assert inp.cursor_pos == 3
    inp.handle_event(key_event("Backspace"))
    assert inp.data == "ab"


def test_input_cursor_movement_and_mid_insert():
    inp = InputLine(Rect(0, 0, 20, 1), text="world")
    inp.cursor_pos = 0
    inp.handle_event(key_event("End"))
    assert inp.cursor_pos == 5
    inp.handle_event(key_event("Home"))
    assert inp.cursor_pos == 0
    inp.insert("hello ")
    assert inp.data == "hello world"


def test_input_horizontal_scroll():
    inp = InputLine(Rect(0, 0, 5, 1))
    inp.state |= State.FOCUSED
    inp.insert("abcdefgh")
    # Caret at end, width 5 -> first must have advanced so caret is visible.
    assert inp.first > 0
    inp.draw(_ctx(inp, 5, 1))
    assert inp.cursor is not None
    assert inp.cursor.x <= 4


def test_input_selection_and_delete():
    inp = InputLine(Rect(0, 0, 20, 1), text="abcdef")
    inp.cursor_pos = 6
    inp.sel_anchor = 2
    assert inp.selected_text() == "cdef"
    inp.handle_event(key_event("Backspace"))
    assert inp.data == "ab"


def test_input_paste_strips_newlines():
    inp = InputLine(Rect(0, 0, 20, 1))
    inp.handle_event(paste_event("one\ntwo"))
    assert inp.data == "one two"


def test_input_max_length():
    inp = InputLine(Rect(0, 0, 20, 1), max_length=3)
    inp.insert("abcdef")
    assert inp.data == "abc"


# --- ListBox + ScrollBar --------------------------------------------------

def test_listbox_navigation_and_scroll():
    sb = ScrollBar(Rect(0, 0, 1, 5))
    lb = ListBox(Rect(0, 0, 10, 5), [f"i{n}" for n in range(20)], scrollbar=sb)
    assert lb.focused_index == 0
    lb.handle_event(key_event("End"))
    assert lb.focused_index == 19
    assert lb.top == 15  # last page
    assert sb.value == lb.top
    lb.handle_event(key_event("Home"))
    assert lb.focused_index == 0 and lb.top == 0


def test_listbox_enter_emits_ok():
    prog = new_prog()
    dlg = Dialog(Rect(0, 0, 20, 12), "D")
    lb = ListBox(Rect(1, 1, 15, 8), ["a", "b"])
    dlg.insert(lb)
    prog.desktop.insert(dlg)
    lb.handle_event(key_event("Enter"))
    assert Command.OK in drain_commands(prog)


def test_listbox_draw_marks_focused_row():
    prog = new_prog(20, 10)
    dlg = Dialog(Rect(0, 0, 18, 9), "D")
    lb = ListBox(Rect(1, 1, 14, 5), ["alpha", "beta", "gamma"])
    dlg.insert(lb)
    prog.desktop.insert(dlg)
    prog.desktop.focus_child(dlg)
    dlg.set_state(State.FOCUSED, True)
    lb.focus()
    prog.redraw()
    o = lb.abs_origin()
    row0 = prog.screen.back.row_text(o.y)
    assert "alpha" in row0


# --- Menu -----------------------------------------------------------------

def menu_prog():
    prog = new_prog(50, 15)
    bar = MenuBar(Rect(0, 0, 50, 1), [
        SubMenu("~F~ile", [MenuItem("~N~ew", 101), MenuItem("E~x~it", Command.QUIT)]),
        SubMenu("~H~elp", [MenuItem("~A~bout", 102)]),
    ])
    prog.set_menu_bar(bar)
    return prog, bar


def test_menu_opens_with_alt_hotkey():
    prog, bar = menu_prog()
    bar.handle_event(key_event("F", Mod.ALT))
    assert bar.active
    assert prog.menu_popup is not None


def test_menu_f10_opens_first():
    prog, bar = menu_prog()
    bar.handle_event(key_event("F10"))
    assert bar.active and bar.open_index == 0


def test_menu_navigate_and_select_emits_command():
    prog, bar = menu_prog()
    bar.open(0)
    bar.handle_event(key_event("Down"))  # move to Exit
    bar.handle_event(key_event("Enter"))
    assert not bar.active
    assert Command.QUIT in drain_commands(prog)


def test_menu_item_hotkey_selects():
    prog, bar = menu_prog()
    bar.open(1)  # Help
    bar.handle_event(key_event("A"))  # About hotkey
    assert 102 in drain_commands(prog)


def test_menu_esc_closes():
    prog, bar = menu_prog()
    bar.open(0)
    bar.handle_event(key_event("Esc"))
    assert not bar.active and prog.menu_popup is None


# --- StatusLine -----------------------------------------------------------

def test_status_line_key_maps_to_command():
    prog = new_prog()
    sl = StatusLine(Rect(0, 19, 60, 20), [
        StatusItem("~F2~ Dialog", "F2", 201),
        StatusItem("~Alt-X~ Exit", "Alt+X", Command.QUIT),
    ])
    prog.set_status_line(sl)
    ev = key_event("F2")
    sl.handle_event(ev)
    assert ev.handled
    assert 201 in drain_commands(prog)
    ev2 = key_event("X", Mod.ALT)
    sl.handle_event(ev2)
    assert Command.QUIT in drain_commands(prog)


# --- Window / Dialog frame -----------------------------------------------

def test_window_frame_and_title_drawn():
    prog = new_prog(30, 10)
    win = Window(Rect(2, 2, 24, 8), "Hello")
    prog.desktop.insert(win)
    win.set_state(State.ACTIVE, True)
    prog.redraw()
    o = win.abs_origin()
    top = prog.screen.back.row_text(o.y)
    assert "Hello" in top
    # corners present (double frame when active).
    assert prog.screen.back.chars[o.y][o.x] in ("╔", "┌")


# --- message box ----------------------------------------------------------

def test_build_message_box_has_buttons():
    dlg = build_message_box(60, 20, "Save changes?", "Confirm", OK_CANCEL)
    buttons = [c for c in dlg.children if isinstance(c, Button)]
    assert {b.command for b in buttons} == {Command.OK, Command.CANCEL}
    assert dlg.title == "Confirm"


def _ctx(view, w, h):
    from py_tvision.geometry import Point
    from py_tvision.screen import Buffer, DrawContext

    buf = Buffer(w, h)
    return DrawContext(buf, Point(0, 0), Rect(0, 0, w, h))
