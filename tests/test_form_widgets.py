# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Form-input widgets: clusters, combo box, memo, spinner, password, dialog."""

import os
import stat
import tempfile
from pathlib import Path

from py_tvision.app import Program
from py_tvision.events import (
    Command,
    EventKind,
    Mod,
    key_event,
    mouse_event,
    paste_event,
)
from py_tvision.geometry import Point, Rect
from py_tvision.platform.headless import HeadlessTerminal
from py_tvision.screen import Buffer, DrawContext
from py_tvision.views import State
from py_tvision.widgets import (
    CheckBoxes,
    ComboBox,
    FileDialog,
    InputLine,
    Memo,
    RadioButtons,
    ScrollBar,
    Spinner,
)
from py_tvision.window import Dialog


def new_prog(w=60, h=24):
    return Program(HeadlessTerminal(w, h), theme="classic")


def drain_commands(prog):
    return [e.command for e in prog.post_queue.drain()
            if getattr(e, "kind", None) in (EventKind.COMMAND, EventKind.BROADCAST)]


def _ctx(w, h):
    buf = Buffer(w, h)
    return buf, DrawContext(buf, Point(0, 0), Rect(0, 0, w, h))


def _in_dialog(prog, widget, dlg_bounds=Rect(0, 0, 40, 18)):
    dlg = Dialog(dlg_bounds, "D")
    dlg.insert(widget)
    prog.desktop.insert(dlg)
    prog.desktop.focus_child(dlg)
    dlg.set_state(State.FOCUSED, True)
    widget.focus()
    return dlg


# --- CheckBoxes -----------------------------------------------------------

def test_checkboxes_space_toggles_and_value_is_set():
    cb = CheckBoxes(Rect(0, 0, 20, 3), ["Alpha", "Beta", "Gamma"])
    cb.state |= State.FOCUSED
    assert cb.value == set()
    cb.handle_event(key_event(" "))
    assert cb.value == {0}
    cb.handle_event(key_event("Down"))
    cb.handle_event(key_event(" "))
    assert cb.value == {0, 1}
    assert cb.mask == 0b011
    cb.handle_event(key_event(" "))  # toggle off item 1
    assert cb.value == {0}


def test_checkboxes_mask_setter():
    cb = CheckBoxes(Rect(0, 0, 20, 3), ["a", "b", "c"])
    cb.mask = 0b101
    assert cb.value == {0, 2}


def test_checkboxes_alt_hotkey_toggles_item():
    prog = new_prog()
    cb = CheckBoxes(Rect(2, 2, 20, 3), ["~A~lpha", "~B~eta"])
    _in_dialog(prog, cb)
    cb.handle_event(key_event("B", Mod.ALT))
    assert cb.value == {1}


def test_checkboxes_mouse_click_toggles_row():
    prog = new_prog()
    cb = CheckBoxes(Rect(2, 2, 20, 5), ["a", "b", "c"])
    _in_dialog(prog, cb)
    o = cb.abs_origin()
    cb.handle_event(mouse_event(EventKind.MOUSE_DOWN, o.x + 1, o.y + 2))
    assert cb.value == {2}


def test_checkboxes_draw_shows_mark():
    cb = CheckBoxes(Rect(0, 0, 14, 2), ["Alpha", "Beta"])
    cb.value = {0}
    cb.state |= State.FOCUSED
    buf, ctx = _ctx(14, 2)
    cb.draw(ctx)
    assert "[X] Alpha" in buf.row_text(0)
    assert "[ ] Beta" in buf.row_text(1)


# --- RadioButtons ---------------------------------------------------------

def test_radiobuttons_arrows_change_selection():
    rb = RadioButtons(Rect(0, 0, 20, 3), ["One", "Two", "Three"], selected=1)
    rb.state |= State.FOCUSED
    assert rb.value == 1
    rb.handle_event(key_event("Down"))
    assert rb.value == 2
    rb.handle_event(key_event("Up"))
    rb.handle_event(key_event("Up"))
    assert rb.value == 0


def test_radiobuttons_alt_hotkey_selects():
    prog = new_prog()
    rb = RadioButtons(Rect(2, 2, 20, 3), ["~O~ne", "~T~wo", "T~h~ree"])
    _in_dialog(prog, rb)
    rb.handle_event(key_event("H", Mod.ALT))
    assert rb.value == 2
    assert rb.selected_label() == "Three"


def test_radiobuttons_draw_marks_selected():
    rb = RadioButtons(Rect(0, 0, 12, 2), ["One", "Two"], selected=1)
    buf, ctx = _ctx(12, 2)
    rb.draw(ctx)
    assert "( ) One" in buf.row_text(0)
    assert "(o) Two" in buf.row_text(1)


# --- ComboBox -------------------------------------------------------------

def test_combobox_initial_value_and_draw():
    cb = ComboBox(Rect(0, 0, 12, 1), ["red", "green", "blue"], index=1)
    assert cb.value == "green"
    buf, ctx = _ctx(12, 1)
    cb.draw(ctx)
    row = buf.row_text(0)
    assert "green" in row
    assert "▼" in row


def test_combobox_value_setter():
    cb = ComboBox(Rect(0, 0, 12, 1), ["red", "green", "blue"])
    cb.value = "blue"
    assert cb.index == 2


def test_combobox_open_picks_item():
    prog = new_prog(40, 20)
    combo = ComboBox(Rect(2, 2, 16, 3), ["one", "two", "three"], index=0)
    _in_dialog(prog, combo)
    # Script the popup: move down once, then Enter to accept.
    prog.terminal.feed_events(key_event("Down"), key_event("Enter"))
    combo.open()
    assert combo.index == 1
    assert combo.value == "two"


def test_combobox_open_esc_cancels():
    prog = new_prog(40, 20)
    combo = ComboBox(Rect(2, 2, 16, 3), ["one", "two", "three"], index=0)
    _in_dialog(prog, combo)
    prog.terminal.feed_events(key_event("Down"), key_event("Esc"))
    combo.open()
    assert combo.index == 0  # unchanged on cancel


# --- Memo -----------------------------------------------------------------

def test_memo_text_roundtrip():
    m = Memo(Rect(0, 0, 10, 4), "ab\ncd")
    assert m.lines == ["ab", "cd"]
    assert m.value == "ab\ncd"


def test_memo_insert_and_newline_and_backspace():
    m = Memo(Rect(0, 0, 10, 4), "abc")
    m.handle_event(key_event("Home"))
    m.handle_event(key_event("Right"))
    m.handle_event(key_event("Enter"))
    assert m.lines == ["a", "bc"]
    assert (m.row, m.col) == (1, 0)
    m.handle_event(key_event("Backspace"))
    assert m.lines == ["abc"]
    assert (m.row, m.col) == (0, 1)


def test_memo_typing_inserts_at_cursor():
    m = Memo(Rect(0, 0, 10, 4), "ac")
    m.handle_event(key_event("Home"))
    m.handle_event(key_event("Right"))
    m.handle_event(key_event("B", text="b"))
    assert m.value == "abc"


def test_memo_max_length_cap():
    m = Memo(Rect(0, 0, 10, 4), "", max_length=3)
    m.handle_event(paste_event("abcdef"))
    assert len(m.value) <= 3


def test_memo_vertical_scroll_and_scrollbar():
    sb = ScrollBar(Rect(0, 0, 1, 4))
    m = Memo(Rect(0, 0, 10, 4), "\n".join(f"line{i}" for i in range(10)),
             vscrollbar=sb)
    for _ in range(9):
        m.handle_event(key_event("Down"))
    assert m.row == 9
    assert m.top > 0
    assert sb.value == m.top


def test_memo_cursor_when_focused():
    m = Memo(Rect(0, 0, 10, 3), "hi\nthere")
    m.state |= State.FOCUSED
    m.row, m.col = 1, 3
    buf, ctx = _ctx(10, 3)
    m.draw(ctx)
    assert m.cursor == Point(3, 1)


def test_memo_mouse_positions_caret():
    prog = new_prog()
    m = Memo(Rect(1, 1, 11, 5), "hello\nworld")
    _in_dialog(prog, m)
    o = m.abs_origin()
    m.handle_event(mouse_event(EventKind.MOUSE_DOWN, o.x + 3, o.y + 1))
    assert (m.row, m.col) == (1, 3)


# --- Spinner --------------------------------------------------------------

def test_spinner_steps_and_clamps():
    sp = Spinner(Rect(0, 0, 8, 1), value=5, minimum=0, maximum=10, step=2)
    assert sp.data == "5"
    sp.handle_event(key_event("Up"))
    assert sp.value == 7 and sp.data == "7"
    sp.handle_event(key_event("Up"))  # 9
    sp.handle_event(key_event("Up"))  # 11 -> clamp 10
    assert sp.value == 10
    sp.handle_event(key_event("Down"))
    assert sp.value == 8


def test_spinner_rejects_letters_accepts_digits():
    sp = Spinner(Rect(0, 0, 8, 1), value=0, minimum=0, maximum=999)
    sp.handle_event(key_event("A", text="a"))
    assert sp.data == "0"  # letter swallowed
    sp.handle_event(key_event("5", text="5"))
    assert "5" in sp.data


def test_spinner_wheel_steps():
    sp = Spinner(Rect(0, 0, 8, 1), value=1, minimum=0, maximum=9, step=1)
    o = sp.bounds  # standalone: abs_origin is (0,0)
    sp.handle_event(mouse_event(EventKind.MOUSE_WHEEL, 0, 0, wheel=1))
    assert sp.value == 2


def test_spinner_float_mode():
    sp = Spinner(Rect(0, 0, 8, 1), value=1.5, minimum=0.0, maximum=5.0,
                 step=0.5, integer=False, decimals=1)
    assert sp.data == "1.5"
    sp.handle_event(key_event("Up"))
    assert sp.value == 2.0 and sp.data == "2.0"
    assert sp._accepts(".") is False  # already present once formatted


def test_spinner_negative_sign_allowed_when_min_negative():
    sp = Spinner(Rect(0, 0, 8, 1), value=0, minimum=-5, maximum=5)
    sp.set_value(0)
    sp.data = ""  # emulate cleared field
    assert sp._accepts("-") is True
    pos = Spinner(Rect(0, 0, 8, 1), value=0, minimum=0, maximum=5)
    pos.data = ""
    assert pos._accepts("-") is False


# --- InputLine password mode ----------------------------------------------

def test_password_masks_on_screen():
    inp = InputLine(Rect(0, 0, 10, 1), password=True)
    inp.state |= State.FOCUSED
    for ch in "secret":
        inp.handle_event(key_event(ch.upper(), text=ch))
    assert inp.data == "secret"
    buf, ctx = _ctx(10, 1)
    inp.draw(ctx)
    row = buf.row_text(0)
    assert "secret" not in row
    assert "••••••" in row


def test_password_repr_hides_value():
    inp = InputLine(Rect(0, 0, 10, 1), password=True, text="hunter2")
    assert "hunter2" not in repr(inp)
    assert "password" in repr(inp)


def test_password_not_copied_to_clipboard():
    prog = new_prog()
    inp = InputLine(Rect(2, 2, 12, 3), password=True, text="secret")
    _in_dialog(prog, inp)
    inp.sel_anchor = 0
    inp.cursor_pos = 6
    inp.handle_event(key_event("C", Mod.CTRL))
    assert prog.get_clipboard() == ""


def test_normal_inputline_repr_shows_data():
    inp = InputLine(Rect(0, 0, 10, 1), text="hi")
    assert "hi" in repr(inp)


# --- FileDialog -----------------------------------------------------------

def _make_tree():
    tmp = Path(tempfile.mkdtemp(prefix="pytv_"))
    (tmp / "alpha").mkdir()
    (tmp / "beta").mkdir()
    (tmp / "note.txt").write_text("x", encoding="utf-8")
    (tmp / "pic.png").write_bytes(b"\x89PNG")
    return tmp


def test_filedialog_lists_folders_first_folder_only():
    tmp = _make_tree()
    try:
        dlg = FileDialog(Rect(0, 0, 40, 16), start_dir=tmp, folders_only=True)
        items = dlg.dir_list.items
        assert items[0] == ".."
        assert "alpha/" in items and "beta/" in items
        # No files in folder-only mode.
        assert "note.txt" not in items
    finally:
        _rmtree(tmp)


def test_filedialog_descend_and_confirm_returns_directory():
    tmp = _make_tree()
    try:
        dlg = FileDialog(Rect(0, 0, 40, 16), start_dir=tmp, folders_only=True)
        idx = dlg.dir_list.items.index("alpha/")
        dlg.dir_list.focused_index = idx
        dlg._activate_entry()
        assert dlg.cwd == (tmp / "alpha").resolve()
        dlg._confirm()
        assert dlg.result_path == (tmp / "alpha").resolve()
        assert dlg.result_path.is_dir()
    finally:
        _rmtree(tmp)


def test_filedialog_go_up():
    tmp = _make_tree()
    try:
        dlg = FileDialog(Rect(0, 0, 40, 16), start_dir=tmp / "alpha",
                         folders_only=True)
        dlg.dir_list.focused_index = 0  # ".."
        dlg._activate_entry()
        assert dlg.cwd == tmp.resolve()
    finally:
        _rmtree(tmp)


def test_filedialog_folder_only_never_returns_a_file():
    tmp = _make_tree()
    try:
        dlg = FileDialog(Rect(0, 0, 40, 16), start_dir=tmp, folders_only=True)
        dlg._confirm()
        assert dlg.result_path is not None
        assert dlg.result_path.is_dir()
    finally:
        _rmtree(tmp)


def test_filedialog_file_mode_returns_file_with_filter():
    tmp = _make_tree()
    try:
        dlg = FileDialog(Rect(0, 0, 40, 16), start_dir=tmp, folders_only=False,
                         extensions=[".txt"])
        items = dlg.dir_list.items
        assert "note.txt" in items
        assert "pic.png" not in items  # filtered out
        dlg.dir_list.focused_index = items.index("note.txt")
        dlg._activate_entry()
        assert dlg.result_path == tmp.resolve() / "note.txt"
        assert dlg._modal_result == Command.OK
    finally:
        _rmtree(tmp)


def test_filedialog_jump_via_path_line():
    tmp = _make_tree()
    try:
        dlg = FileDialog(Rect(0, 0, 40, 16), start_dir=tmp, folders_only=True)
        dlg.path_line.data = str(tmp / "beta")
        dlg._jump_to_path()
        assert dlg.cwd == (tmp / "beta").resolve()  # resolved, e.g. macOS /private/var
    finally:
        _rmtree(tmp)


def test_filedialog_permission_denied_is_handled():
    if os.name == "nt":
        return  # POSIX permission bits only
    tmp = _make_tree()
    denied = tmp / "locked"
    denied.mkdir()
    os.chmod(denied, 0)
    try:
        dlg = FileDialog(Rect(0, 0, 40, 16), start_dir=tmp, folders_only=True)
        before = dlg.cwd
        dlg._enter_dir(denied)
        assert dlg.cwd == before  # did not descend
        assert "permission" in dlg.note.lower()
    finally:
        os.chmod(denied, stat.S_IRWXU)
        _rmtree(tmp)


def _rmtree(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_dir():
                child.rmdir()
            else:
                child.unlink()
        except OSError:
            try:
                os.chmod(child, stat.S_IRWXU)
                child.unlink()
            except OSError:
                pass
    try:
        path.rmdir()
    except OSError:
        pass
