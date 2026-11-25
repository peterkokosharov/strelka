# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Regression tests for the review findings on the backend/widget commits.

Each test pins one finding so it cannot silently come back: the POSIX escape
deadline (driven through the real ``PosixTerminal.read`` with a fake select,
fake ``os.read`` and an injected clock), lone surrogates, the signal guards,
FileDialog path handling, Memo paste, password paste, ``Program.run`` cleanup,
``NO_COLOR``/mono rendering and Spinner validation. Nothing here touches a
real terminal or sends a real signal.
"""

import os
import time
from pathlib import Path

import pytest

import py_tvision.app as app_mod
import py_tvision.platform.posix as posix_mod
import py_tvision.widgets.folderdlg as folderdlg_mod
from py_tvision.app import Program, install_terminal_guards
from py_tvision.color import DEPTH_16, DEPTH_MONO, detect_depth, sgr
from py_tvision.events import Command, EventKind, Mod, key_event, paste_event
from py_tvision.geometry import Rect
from py_tvision.platform.headless import HeadlessTerminal
from py_tvision.platform.posix import PosixTerminal
from py_tvision.platform.vtinput import VTInputDecoder
from py_tvision.platform.win32 import utf16_units, write_console_w
from py_tvision.screen import Buffer, Screen
from py_tvision.text import SAFE_PLACEHOLDER, is_unsafe_control, safe_glyph
from py_tvision.theme import Style, get_theme
from py_tvision.views import State
from py_tvision.widgets import FileDialog, InputLine, Memo, Spinner
from py_tvision.window import Dialog


# ===========================================================================
# 1. POSIX lone-ESC deadline (HIGH)
# ===========================================================================

TTY_FD = 9101
WAKE_FD = 9102


class _Clock:
    """Injected monotonic clock; tests move time explicitly."""

    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t


class _ScriptedSelect:
    """Fake ``select`` module. Each call consumes one scripted step
    ``(tty_bytes, wake_bytes, elapsed)``: time advances by ``elapsed`` and the
    listed fds become readable with those bytes."""

    def __init__(self, clock: _Clock, steps):
        self.clock = clock
        self.steps = list(steps)
        self.timeouts: list = []
        self.data: dict[int, bytes] = {}

    def select(self, rlist, _w, _x, timeout):
        self.timeouts.append(timeout)
        tty, wake, elapsed = self.steps.pop(0)
        self.clock.t += elapsed
        self.data = {TTY_FD: tty, WAKE_FD: wake}
        ready = [fd for fd, b in self.data.items() if b and fd in rlist]
        return ready, [], []


def _posix_term(monkeypatch, steps):
    """A PosixTerminal whose read() runs for real against fakes."""
    clock = _Clock()
    sel = _ScriptedSelect(clock, steps)
    term = PosixTerminal.__new__(PosixTerminal)
    term._fd = TTY_FD
    term._wake_r = WAKE_FD
    term._decoder = VTInputDecoder()
    term._select = sel
    term._clock = clock
    term._esc_deadline = None

    def fake_read(fd, _n):
        data = sel.data.get(fd, b"")
        sel.data[fd] = b""
        return data

    monkeypatch.setattr(posix_mod.os, "read", fake_read)
    return term, sel, clock


def test_split_csi_across_wake_keeps_bytes_and_decodes_ctrl_up(monkeypatch):
    term, sel, _ = _posix_term(monkeypatch, [
        (b"\x1b[1;5", b"", 0.0),   # first half of Ctrl+Up
        (b"", b".", 0.01),         # Program.post wakes the loop mid-sequence
        (b"A", b"", 0.005),        # the rest of the sequence
    ])
    assert term.read(None) == []
    assert term.read(None) == []  # the wake must NOT flush the partial CSI
    evs = term.read(None)
    assert len(evs) == 1
    assert evs[0].key == "Up" and evs[0].mods == Mod.CTRL


def test_split_sgr_mouse_across_wake_is_a_mouse_event(monkeypatch):
    term, _, _ = _posix_term(monkeypatch, [
        (b"\x1b[<0;12;", b"", 0.0),
        (b"", b".", 0.002),
        (b"5M", b"", 0.002),
    ])
    out = term.read(None) + term.read(None) + term.read(None)
    assert len(out) == 1
    ev = out[0]
    assert ev.kind == EventKind.MOUSE_DOWN
    assert (ev.mouse.x, ev.mouse.y) == (11, 4)
    assert not any(e.kind == EventKind.KEY for e in out)


def test_split_csi_across_sigwinch_keeps_bytes_and_reports_resize(monkeypatch):
    term, _, _ = _posix_term(monkeypatch, [
        (b"\x1b[1;5", b"", 0.0),
        (b"", b"W", 0.01),         # SIGWINCH self-pipe byte
        (b"A", b"", 0.005),
    ])
    assert term.read(None) == []
    mid = term.read(None)
    assert [e.kind for e in mid] == [EventKind.RESIZE]
    evs = term.read(None)
    assert evs[0].key == "Up" and evs[0].mods == Mod.CTRL


def test_lone_esc_becomes_esc_after_deadline(monkeypatch):
    term, sel, _ = _posix_term(monkeypatch, [
        (b"\x1b", b"", 0.0),
        (b"", b"", 0.05),          # the bounded wait ran out
    ])
    assert term.read(None) == []
    evs = term.read(None)
    assert [e.key for e in evs] == ["Esc"]
    # The second wait was bounded by the escape deadline, not infinite.
    assert sel.timeouts[1] == pytest.approx(0.05)
    assert not term._decoder.pending_escape()


def test_short_timer_before_deadline_does_not_flush(monkeypatch):
    term, sel, _ = _posix_term(monkeypatch, [
        (b"\x1b", b"", 0.0),
        (b"", b"", 0.01),          # an app timer due in 10 ms fires first
        (b"", b"", 0.04),          # now the full 50 ms have passed
    ])
    assert term.read(None) == []
    assert term.read(0.01) == []  # short timer: keep waiting, no Esc yet
    assert term._decoder.pending_escape()
    assert sel.timeouts[1] == pytest.approx(0.01)
    evs = term.read(None)
    assert [e.key for e in evs] == ["Esc"]
    # Only the remaining part of the deadline was waited for.
    assert sel.timeouts[2] == pytest.approx(0.04)


def test_short_timer_then_continuation_is_alt_key_not_esc(monkeypatch):
    term, _, _ = _posix_term(monkeypatch, [
        (b"\x1b", b"", 0.0),
        (b"", b"", 0.01),
        (b"x", b"", 0.01),
    ])
    assert term.read(None) == []
    assert term.read(0.01) == []
    evs = term.read(None)
    assert len(evs) == 1 and evs[0].key == "X" and evs[0].mods == Mod.ALT


def test_new_bytes_restart_the_escape_deadline(monkeypatch):
    term, _, _ = _posix_term(monkeypatch, [
        (b"\x1b", b"", 0.0),
        (b"[1;", b"", 0.04),       # more of the sequence at t=40 ms
        (b"", b".", 0.03),         # t=70 ms: past the FIRST deadline only
        (b"", b"", 0.03),          # t=100 ms: past the restarted deadline
    ])
    assert term.read(None) == []
    assert term.read(None) == []
    assert term.read(None) == []   # deadline restarted at 40 ms -> no flush
    assert [e.key for e in term.read(None)] == ["Esc"]


def test_completed_sequence_clears_the_deadline(monkeypatch):
    term, sel, _ = _posix_term(monkeypatch, [
        (b"\x1b[A", b"", 0.0),
        (b"", b"", 0.5),
    ])
    assert [e.key for e in term.read(None)] == ["Up"]
    assert term.read(None) == []
    # Nothing pending: the caller's timeout (None = block) is not bounded.
    assert sel.timeouts[1] is None


def test_pending_escape_bounds_a_long_caller_timeout(monkeypatch):
    term, sel, _ = _posix_term(monkeypatch, [
        (b"\x1b", b"", 0.0),
        (b"", b"", 0.02),
        (b"", b"", 0.03),
    ])
    term.read(5.0)
    assert sel.timeouts[0] == 5.0
    assert term.read(5.0) == []       # 20 ms in: not yet
    assert sel.timeouts[1] == pytest.approx(0.05)
    assert [e.key for e in term.read(5.0)] == ["Esc"]
    assert sel.timeouts[2] == pytest.approx(0.03)


# ===========================================================================
# 2. Lone surrogates (HIGH)
# ===========================================================================

def test_utf16_units_survives_lone_surrogate():
    assert utf16_units("a\ud800b") == 3
    assert utf16_units("\udfff") == 1
    assert utf16_units("a\U0001F600") == 3


def test_write_console_w_with_lone_surrogate_does_not_raise():
    class K32:
        def __init__(self):
            self.calls = []

        def WriteConsoleW(self, handle, text, length, ref, reserved):
            self.calls.append(length)
            return 1

    k32 = K32()
    write_console_w(k32, 1, "x\ud800y", object())
    assert k32.calls == [3]


def test_lone_surrogates_are_unsafe_and_replaced():
    for ch in ("\ud800", "\udbff", "\udc00", "\udfff"):
        assert is_unsafe_control(ch)
        assert safe_glyph(ch) == SAFE_PLACEHOLDER
    assert not is_unsafe_control("\ud7ff")
    assert not is_unsafe_control("\ue000")
    assert safe_glyph("\U0001F600") == "\U0001F600"


def test_set_cell_replaces_lone_surrogate_and_flush_encodes_strictly():
    scr = Screen(4, 1)
    scr.back.set_cell(0, 0, "\ud800", Style())
    assert scr.back.chars[0][0] == SAFE_PLACEHOLDER
    out = scr.flush()
    out.encode("utf-8")  # strict: would raise on a surrogate
    out.encode("utf-16-le")


# ===========================================================================
# 3. Signal guards (MED)
# ===========================================================================

class _Sig:
    SIG_DFL = "DFL"
    SIG_IGN = "IGN"
    SIGTERM = 15
    SIGHUP = 1

    def __init__(self, initial=None):
        self.installed = dict(initial or {})

    def getsignal(self, sig):
        return self.installed.get(sig, self.SIG_DFL)

    def signal(self, sig, handler):
        if handler is None:
            raise TypeError("signal handler must be signal.SIG_IGN, "
                            "signal.SIG_DFL, or a callable object")
        prev = self.getsignal(sig)
        self.installed[sig] = handler
        return prev


class _Os:
    def __init__(self):
        self.killed = []

    def getpid(self):
        return 4242

    def kill(self, pid, sig):
        self.killed.append((pid, sig))


class _Atexit:
    def __init__(self):
        self.registered = []
        self.unregistered = []

    def register(self, fn):
        self.registered.append(fn)

    def unregister(self, fn):
        self.unregistered.append(fn)


class _Term:
    is_headless = True

    def __init__(self, stop_error=None):
        self.stop_calls = 0
        self.stop_error = stop_error

    def stop(self):
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error


def _guards(term, sig):
    os_ = _Os()
    atx = _Atexit()
    g = install_terminal_guards(term, atexit_mod=atx, signal_mod=sig, os_mod=os_)
    return g, os_, atx


def test_guard_does_not_override_sig_ign():
    sig = _Sig({_Sig.SIGHUP: _Sig.SIG_IGN})  # e.g. started under nohup
    g, _, _ = _guards(_Term(), sig)
    assert sig.installed[_Sig.SIGHUP] == _Sig.SIG_IGN
    assert _Sig.SIGHUP not in g.signals
    assert _Sig.SIGTERM in g.signals
    g.uninstall()
    assert sig.installed[_Sig.SIGHUP] == _Sig.SIG_IGN


def test_guard_does_not_override_c_level_handler():
    sig = _Sig({_Sig.SIGTERM: None})  # installed from C: getsignal() is None
    g, _, _ = _guards(_Term(), sig)
    assert sig.installed[_Sig.SIGTERM] is None
    assert _Sig.SIGTERM not in g.signals
    g.uninstall()  # must not try signal(SIGTERM, None) -> TypeError
    assert sig.installed[_Sig.SIGTERM] is None


def test_oserror_during_restore_does_not_escape_signal_handler():
    term = _Term(stop_error=OSError(5, "Input/output error"))  # tty gone
    sig = _Sig()
    g, os_, _ = _guards(term, sig)
    g.handler(_Sig.SIGHUP, None)  # must not raise
    assert term.stop_calls == 1
    assert os_.killed == [(4242, _Sig.SIGHUP)]  # still re-raised


def test_oserror_during_restore_does_not_escape_atexit():
    term = _Term(stop_error=OSError(5, "Input/output error"))
    g, _, atx = _guards(term, _Sig())
    atx.registered[0]()  # what atexit would call
    g.restore()


def test_previous_python_handler_is_chained():
    seen = []

    def previous(signum, frame):
        seen.append((signum, frame))

    term = _Term()
    sig = _Sig({_Sig.SIGTERM: previous})
    g, os_, _ = _guards(term, sig)
    frame = object()
    g.handler(_Sig.SIGTERM, frame)
    assert term.stop_calls == 1           # terminal restored first
    assert seen == [(_Sig.SIGTERM, frame)]  # then the app's own handler ran
    assert os_.killed == []               # no forced default kill


def test_default_disposition_is_reset_and_signal_reraised():
    term = _Term()
    sig = _Sig()
    g, os_, _ = _guards(term, sig)
    assert sig.installed[_Sig.SIGTERM] is g.handler
    g.handler(_Sig.SIGTERM, None)
    assert term.stop_calls == 1
    assert sig.installed[_Sig.SIGTERM] == _Sig.SIG_DFL
    assert os_.killed == [(4242, _Sig.SIGTERM)]


# ===========================================================================
# 4/5/8/9. FileDialog
# ===========================================================================

def _tree(tmp_path: Path) -> Path:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    return tmp_path


def _dlg(start, folders_only=True, extensions=None):
    return FileDialog(Rect(0, 0, 40, 16), start_dir=start,
                      folders_only=folders_only, extensions=extensions)


def test_relative_dotdot_in_path_line_goes_to_parent(tmp_path):
    root = _tree(tmp_path)
    dlg = _dlg(root / "alpha")
    dlg.path_line.data = ".."
    dlg._jump_to_path()
    assert dlg.cwd == root.resolve()
    assert dlg.cwd.is_absolute()


def test_relative_name_in_path_line_resolves_against_dialog_cwd(tmp_path):
    root = _tree(tmp_path)
    dlg = _dlg(root)
    dlg.path_line.data = "beta"
    dlg._jump_to_path()
    assert dlg.cwd == (root / "beta").resolve()
    assert dlg.cwd.is_absolute()


def test_tilde_in_path_line_is_expanded(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.setenv("USERPROFILE", str(root))
    dlg = _dlg(root / "alpha")
    dlg.path_line.data = "~/beta"
    dlg._jump_to_path()
    assert dlg.cwd == (root / "beta").resolve()


def test_path_line_resolve_error_is_reported_not_raised(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    dlg = _dlg(root)
    before = dlg.cwd

    def boom(self, strict=False):
        raise OSError("resolve failed")

    dlg.path_line.data = "beta"
    # Patch Path only around the call so pytest's own reporting is unaffected.
    with monkeypatch.context() as mp:
        mp.setattr(folderdlg_mod.Path, "resolve", boom)
        dlg._jump_to_path()
    assert dlg.cwd == before
    assert "not found" in dlg.note


def test_path_line_is_file_permission_error_is_handled(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    dlg = _dlg(root, folders_only=False)

    def deny(self, *a, **k):
        raise PermissionError("denied")

    dlg.path_line.data = str(root / "note.txt")
    with monkeypatch.context() as mp:
        mp.setattr(folderdlg_mod.Path, "is_file", deny)
        dlg._jump_to_path()  # must not raise
    assert dlg._modal_result is None
    assert dlg.result_path is None
    assert "not found" in dlg.note


def test_drives_use_listdrives_when_available(monkeypatch):
    monkeypatch.setattr(folderdlg_mod.os, "listdrives",
                        lambda: ["C:\\", "Q:\\"], raising=False)

    def no_probe(self, *a, **k):
        raise AssertionError("must not probe drive letters with exists()")

    with monkeypatch.context() as mp:
        mp.setattr(folderdlg_mod.Path, "exists", no_probe)
        drives = FileDialog._drives(object())
    assert drives == [Path("C:\\"), Path("Q:\\")]


def test_drives_fall_back_without_listdrives(monkeypatch):
    monkeypatch.delattr(folderdlg_mod.os, "listdrives", raising=False)
    with monkeypatch.context() as mp:
        mp.setattr(folderdlg_mod.Path, "exists",
                   lambda self: str(self).upper().startswith("D:"))
        drives = FileDialog._drives(object())
    assert drives == [Path("D:\\")]


def test_drives_fall_back_when_listdrives_fails(monkeypatch):
    def broken():
        raise OSError("no")

    monkeypatch.setattr(folderdlg_mod.os, "listdrives", broken, raising=False)
    with monkeypatch.context() as mp:
        mp.setattr(folderdlg_mod.Path, "exists",
                   lambda self: str(self).upper().startswith("E:"))
        drives = FileDialog._drives(object())
    assert drives == [Path("E:\\")]


def _assert_never_ok_without_path(dlg):
    if dlg._modal_result == Command.OK:
        assert dlg.result_path is not None


def test_ok_in_drive_list_descends_instead_of_ok_none(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    dlg = _dlg(root / "alpha")
    monkeypatch.setattr(dlg, "_drives", lambda: [root])
    dlg.drives_mode = True
    dlg._refresh()
    dlg.dir_list.focused_index = 0
    dlg._confirm()
    _assert_never_ok_without_path(dlg)
    assert dlg._modal_result is None   # stays open...
    assert not dlg.drives_mode         # ...inside the chosen drive
    assert dlg.cwd.resolve() == root.resolve()


def test_ok_in_empty_drive_list_stays_open(tmp_path, monkeypatch):
    dlg = _dlg(_tree(tmp_path))
    monkeypatch.setattr(dlg, "_drives", lambda: [])
    dlg.drives_mode = True
    dlg._refresh()
    dlg._confirm()
    assert dlg._modal_result is None
    assert dlg.result_path is None


def test_ok_on_focused_folder_in_file_mode_descends(tmp_path):
    root = _tree(tmp_path)
    dlg = _dlg(root, folders_only=False)
    dlg.dir_list.focused_index = dlg.dir_list.items.index("alpha/")
    dlg._confirm()
    assert dlg._modal_result is None
    assert dlg.cwd == (root / "alpha").resolve()


def test_ok_never_returns_none_for_any_entry(tmp_path):
    root = _tree(tmp_path)
    for folders_only in (True, False):
        for i in range(4):
            dlg = _dlg(root, folders_only=folders_only)
            if i >= len(dlg.dir_list.items):
                continue
            dlg.dir_list.focused_index = i
            dlg._confirm()
            _assert_never_ok_without_path(dlg)


def test_start_dir_that_is_a_file_opens_its_parent(tmp_path):
    root = _tree(tmp_path)
    dlg = _dlg(root / "note.txt", folders_only=False)
    assert dlg.cwd == root.resolve()
    assert "note.txt" in dlg.dir_list.items


def test_missing_start_dir_opens_nearest_existing_parent(tmp_path):
    root = _tree(tmp_path)
    dlg = _dlg(root / "alpha" / "gone" / "deeper")
    assert dlg.cwd == (root / "alpha").resolve()


def test_vanished_file_is_not_returned(tmp_path):
    root = _tree(tmp_path)
    dlg = _dlg(root, folders_only=False)
    dlg.dir_list.focused_index = dlg.dir_list.items.index("note.txt")
    (root / "note.txt").unlink()  # gone (or a dangling link) since listing
    dlg._activate_entry()
    assert dlg.result_path is None
    assert dlg._modal_result is None
    dlg._confirm()
    assert dlg.result_path is None
    assert dlg._modal_result is None


def test_broken_symlink_is_not_listed_or_returned(tmp_path):
    root = _tree(tmp_path)
    link = root / "dangling.txt"
    try:
        os.symlink(root / "missing.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available here")
    dlg = _dlg(root, folders_only=False)
    assert "dangling.txt" not in dlg.dir_list.items
    dlg.path_line.data = str(link)
    dlg._jump_to_path()
    assert dlg.result_path is None
    assert dlg._modal_result is None


# ===========================================================================
# 6. Memo paste
# ===========================================================================

def test_memo_paste_normalises_crlf_and_cr():
    m = Memo(Rect(0, 0, 20, 5), "")
    m.handle_event(paste_event("a\r\nb\rc\nd"))
    assert m.lines == ["a", "b", "c", "d"]
    assert (m.row, m.col) == (3, 1)


def test_memo_paste_splices_into_middle_of_line():
    m = Memo(Rect(0, 0, 20, 5), "XY")
    m.row, m.col = 0, 1
    m.handle_event(paste_event("1\r\n2"))
    assert m.lines == ["X1", "2Y"]
    assert (m.row, m.col) == (1, 1)


def test_memo_large_paste_is_fast():
    text = "\n".join(f"line {i:05d} of the pasted block" for i in range(5000))
    m = Memo(Rect(0, 0, 40, 10), "", max_length=10_000_000)
    t0 = time.perf_counter()
    m.handle_event(paste_event(text))
    elapsed = time.perf_counter() - t0
    assert m.value == text
    assert len(m.lines) == 5000
    assert elapsed < 1.0, f"5000-line paste took {elapsed:.2f}s"


def test_memo_paste_respects_max_length():
    m = Memo(Rect(0, 0, 20, 5), "", max_length=10)
    m.handle_event(paste_event("abc\ndef\nghijkl"))
    assert m.value == "abc\ndef\ngh"
    assert len(m.value) == 10
    m.handle_event(paste_event("more"))
    assert len(m.value) == 10


def test_memo_paste_max_length_counts_crlf_as_one():
    m = Memo(Rect(0, 0, 20, 5), "", max_length=4)
    m.handle_event(paste_event("ab\r\ncd"))
    assert m.value == "ab\nc"


def test_memo_paste_max_length_with_existing_text():
    m = Memo(Rect(0, 0, 20, 5), "1234", max_length=6)
    m.row, m.col = 0, 2
    m.handle_event(paste_event("ab\ncd"))
    assert m.value == "12ab34"


# ===========================================================================
# 7. Password: paste allowed, copy/cut inert
# ===========================================================================

def _prog_with(widget):
    prog = Program(HeadlessTerminal(60, 24), theme="classic")
    dlg = Dialog(Rect(0, 0, 40, 18), "D")
    dlg.insert(widget)
    prog.desktop.insert(dlg)
    prog.desktop.focus_child(dlg)
    dlg.set_state(State.FOCUSED, True)
    widget.focus()
    return prog


def test_password_field_accepts_ctrl_v():
    inp = InputLine(Rect(2, 2, 20, 3), password=True)
    prog = _prog_with(inp)
    prog.set_clipboard("pw-from-manager")
    inp.handle_event(key_event("V", Mod.CTRL))
    assert inp.data == "pw-from-manager"
    assert "pw-from-manager" not in repr(inp)


def test_password_field_copy_and_cut_are_inert():
    inp = InputLine(Rect(2, 2, 20, 3), password=True, text="secret")
    prog = _prog_with(inp)
    term = prog.terminal
    inp.sel_anchor, inp.cursor_pos = 0, 6
    inp.handle_event(key_event("C", Mod.CTRL))
    inp.handle_event(key_event("X", Mod.CTRL))
    assert prog.get_clipboard() == ""
    assert term.clipboard is None  # nothing went out via OSC 52 either
    assert inp.data == "secret"    # cut did not delete
    assert "secret" not in repr(inp)


# ===========================================================================
# 10. Program.run uninstalls guards if start() raises
# ===========================================================================

def test_run_uninstalls_guards_when_start_raises(monkeypatch):
    calls = []

    class G:
        def uninstall(self):
            calls.append("uninstall")

    monkeypatch.setattr(app_mod, "install_terminal_guards", lambda t: G())

    class BadTerm(HeadlessTerminal):
        def start(self):
            raise RuntimeError("cannot enable VT")

        def stop(self):
            calls.append("stop")

    prog = Program(BadTerm(40, 10))
    with pytest.raises(RuntimeError):
        prog.run()
    assert "uninstall" in calls
    assert "stop" in calls


# ===========================================================================
# 11. NO_COLOR only when non-empty; mono keeps highlights visible
# ===========================================================================

def test_no_color_empty_is_ignored():
    assert detect_depth({"NO_COLOR": "", "TERM": "xterm-256color"}) != DEPTH_MONO
    assert detect_depth({"NO_COLOR": "1"}) == DEPTH_MONO


def test_mono_light_background_emits_reverse():
    black, white = 0x000000, 0xFFFFFF
    assert ";7" in sgr(black, white, False, False, DEPTH_MONO)
    assert ";7" not in sgr(white, black, False, False, DEPTH_MONO)
    # Bold is kept alongside reverse.
    s = sgr(black, white, True, False, DEPTH_MONO)
    assert ";1" in s and ";7" in s
    # Colour depths are unchanged: no reverse attribute there.
    assert ";7m" not in sgr(black, white, False, False, DEPTH_16)


def test_mono_focused_list_row_is_visible_on_screen():
    theme = get_theme("mono")
    normal = theme.style("list")
    focused = theme.style("list.focused")
    scr = Screen(4, 2, depth=DEPTH_MONO)
    scr.back.set_cell(0, 0, "a", normal)
    scr.back.set_cell(0, 1, "b", focused)
    out = scr.flush()
    normal_sgr = sgr(normal.fg, normal.bg, normal.bold, normal.underline, DEPTH_MONO)
    focused_sgr = sgr(focused.fg, focused.bg, focused.bold, focused.underline, DEPTH_MONO)
    assert normal_sgr != focused_sgr
    assert focused_sgr in out and ";7" in focused_sgr


# ===========================================================================
# 12. Spinner validation
# ===========================================================================

def test_spinner_rejects_unicode_digit_keystroke():
    sp = Spinner(Rect(0, 0, 8, 1), value=5, minimum=0, maximum=999)
    sp.handle_event(key_event("²", text="²"))
    assert sp.data == "5"
    assert sp.value == 5


def test_spinner_rejects_invalid_paste():
    sp = Spinner(Rect(0, 0, 8, 1), value=5, minimum=0, maximum=999)
    for bad in ("12a", "²", "٣", " 7", "1-2", "-3"):  # "-" not allowed: min >= 0
        sp.handle_event(paste_event(bad))
        assert sp.data == "5", bad
    assert sp.value == 5


def test_spinner_accepts_valid_paste():
    sp = Spinner(Rect(0, 0, 8, 1), value=5, minimum=0, maximum=999)
    sp.handle_event(paste_event("42"))
    assert sp.data == "542"
    assert sp.value == 542


def test_spinner_rejects_invalid_ctrl_v():
    sp = Spinner(Rect(2, 2, 10, 3), value=5, minimum=0, maximum=999)
    prog = _prog_with(sp)
    prog.set_clipboard("x9")
    sp.handle_event(key_event("V", Mod.CTRL))
    assert sp.data == "5"
    prog.set_clipboard("9")
    sp.handle_event(key_event("V", Mod.CTRL))
    assert sp.data == "59"


def test_spinner_float_rejects_second_point_by_paste():
    sp = Spinner(Rect(0, 0, 10, 1), value=1.5, minimum=-5.0, maximum=50.0,
                 integer=False, decimals=1)
    sp.handle_event(paste_event(".3"))
    assert sp.data == "1.5"
    sp.data, sp.cursor_pos = "", 0
    sp.handle_event(paste_event("-2.25"))
    assert sp.data == "-2.25"
    assert sp.value == -2.25


def test_spinner_value_ignores_non_ascii_digits():
    sp = Spinner(Rect(0, 0, 8, 1), value=5, minimum=1, maximum=999)
    sp.data = "٣"  # int() would accept Arabic-Indic three
    assert sp.value == 1
