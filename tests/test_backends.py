# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Terminal-backend seams: ESC resolution, UTF-16 write length, kill guards,
colour-depth wiring. All run headlessly; no real console is reached."""

import signal

from py_tvision.app import Program, install_terminal_guards
from py_tvision.color import DEPTH_256, DEPTH_TRUE
from py_tvision.geometry import Rect
from py_tvision.platform.posix import resolve_pending_escape
from py_tvision.platform.vtinput import VTInputDecoder
from py_tvision.platform.win32 import utf16_units, write_console_w


# -- Bug 1: lone-ESC resolution via an injected "byte available" callable ----

def test_resolve_lone_esc_times_out_to_esc():
    dec = VTInputDecoder()
    dec.feed(b"\x1b")
    assert dec.pending_escape()
    # read_more returns nothing -> the bounded wait timed out -> Esc.
    evs = resolve_pending_escape(dec, lambda: b"")
    assert evs and evs[0].key == "Esc"
    assert not dec.pending_escape()


def test_resolve_esc_with_continuation_is_csi():
    dec = VTInputDecoder()
    dec.feed(b"\x1b")
    # A continuation byte arrived within the timeout: ESC + '[A' -> Up.
    evs = resolve_pending_escape(dec, lambda: b"[A")
    assert evs and evs[0].key == "Up"


def test_resolve_esc_with_letter_is_alt():
    dec = VTInputDecoder()
    dec.feed(b"\x1b")
    evs = resolve_pending_escape(dec, lambda: b"q")
    from py_tvision.events import Mod
    assert evs[0].key == "Q" and (evs[0].mods & Mod.ALT)


def test_resolve_ss3_function_key():
    dec = VTInputDecoder()
    dec.feed(b"\x1b")
    evs = resolve_pending_escape(dec, lambda: b"OP")
    assert evs[0].key == "F1"


def test_resolve_stuck_csi_times_out_to_esc():
    dec = VTInputDecoder()
    dec.feed(b"\x1b[")  # partial CSI already buffered
    assert dec.pending_escape()
    evs = resolve_pending_escape(dec, lambda: b"")
    assert evs and evs[0].key == "Esc"
    assert not dec.pending_escape()


# -- Bug 2: WriteConsoleW must count UTF-16 units, not code points ------------

def test_utf16_units_basic():
    assert utf16_units("a") == 1
    assert utf16_units("\U0001F600") == 2  # emoji: 1 code point, 2 UTF-16 units
    assert utf16_units("中") == 1  # BMP CJK: 1 unit
    assert utf16_units("") == 0
    # Mixed: 'a' (1) + emoji (2) + '中' (1) = 4 units, though len() == 3.
    mixed = "a\U0001F600中"
    assert len(mixed) == 3
    assert utf16_units(mixed) == 4


class _FakeK32:
    """Records exactly what WriteConsoleW was asked to write."""

    def __init__(self):
        self.calls = []

    def WriteConsoleW(self, handle, text, length, written_ref, reserved):
        self.calls.append((text, length))
        return 1


def test_write_console_w_passes_utf16_length():
    k32 = _FakeK32()
    text = "ab\U0001F600"  # 'a','b',emoji -> len 3, but 4 UTF-16 units
    write_console_w(k32, 7, text, object())
    assert k32.calls == [(text, 4)]
    # And a plain BMP string: units == len.
    k32.calls.clear()
    write_console_w(k32, 7, "hello", object())
    assert k32.calls == [("hello", 5)]


# -- Bug 3: restore-on-kill guards -------------------------------------------

class _FakeTerminal:
    is_headless = True

    def __init__(self):
        self.started = False
        self.stopped = 0

    def start(self):
        self.started = True

    def stop(self):
        self.stopped += 1  # idempotent counter

    def size(self):
        return 80, 25


class _FakeAtexit:
    def __init__(self):
        self.registered = []
        self.unregistered = []

    def register(self, fn):
        self.registered.append(fn)

    def unregister(self, fn):
        self.unregistered.append(fn)


class _FakeSignal:
    SIG_DFL = "DFL"
    SIG_IGN = "IGN"
    SIGTERM = 15
    SIGHUP = 1  # present here; real Windows lacks it (covered separately)

    def __init__(self):
        self.installed = {}

    def getsignal(self, sig):
        return self.installed.get(sig, self.SIG_DFL)

    def signal(self, sig, handler):
        prev = self.installed.get(sig, self.SIG_DFL)
        self.installed[sig] = handler
        return prev


def test_guards_register_atexit_and_signals():
    term = _FakeTerminal()
    atx = _FakeAtexit()
    sigmod = _FakeSignal()
    guards = install_terminal_guards(term, atexit_mod=atx, signal_mod=sigmod)
    # atexit restore registered.
    assert guards.restore in atx.registered
    # Both SIGTERM and SIGHUP handlers installed (the seam, not a real kill).
    assert sigmod.SIGTERM in guards.signals and sigmod.SIGHUP in guards.signals
    assert sigmod.installed[sigmod.SIGTERM] is guards.handler
    assert sigmod.installed[sigmod.SIGHUP] is guards.handler


class _FakeTermios:
    TCSANOW = 0

    def __init__(self):
        self.set_calls = []

    def tcsetattr(self, fd, when, attrs):
        self.set_calls.append(attrs)


def _started_posix_terminal():
    """A real PosixTerminal in its "started" state, with fake tty plumbing."""
    from py_tvision.platform.posix import PosixTerminal

    class _Captured(PosixTerminal):
        def write(self, text):
            self.written.append(text)

    term = _Captured.__new__(_Captured)
    term.written = []
    term._fd = 9201
    term._termios = _FakeTermios()
    term._old_attrs = ["cooked-attrs"]
    term._started = True
    return term


def test_guards_restore_is_idempotent():
    # The real property: a second restore (atexit after the normal finally, or
    # a signal after atexit) has no further effect on the terminal -- the
    # leave-alt-screen/show-cursor sequence and the tty-mode restore each
    # happen exactly once.
    term = _started_posix_terminal()
    guards = install_terminal_guards(term, atexit_mod=_FakeAtexit(),
                                     signal_mod=_FakeSignal())
    guards.restore()
    assert term._termios.set_calls == [["cooked-attrs"]]
    assert len(term.written) == 1 and "[?1049l" in term.written[0]
    guards.restore()
    guards.restore()
    assert term._termios.set_calls == [["cooked-attrs"]]
    assert len(term.written) == 1


def test_guards_uninstall_restores_previous_handlers():
    term = _FakeTerminal()
    atx = _FakeAtexit()
    sigmod = _FakeSignal()
    guards = install_terminal_guards(term, atexit_mod=atx, signal_mod=sigmod)
    guards.uninstall()
    assert guards.restore in atx.unregistered
    # Previous dispositions (SIG_DFL here) restored.
    assert sigmod.installed[sigmod.SIGTERM] == sigmod.SIG_DFL
    assert sigmod.installed[sigmod.SIGHUP] == sigmod.SIG_DFL


def test_guards_skip_missing_signal_names():
    # A platform without SIGHUP (like Windows) must not blow up.
    class _NoHupSignal(_FakeSignal):
        SIGHUP = None  # getattr(..., "SIGHUP") is None -> skipped

    term = _FakeTerminal()
    sigmod = _NoHupSignal()
    guards = install_terminal_guards(term, atexit_mod=_FakeAtexit(), signal_mod=sigmod)
    assert sigmod.SIGTERM in guards.signals
    assert None not in guards.signals


def test_real_sigterm_handler_registers_and_restores():
    # Exercise the real signal module on the main thread, then restore it, so
    # we prove registration end-to-end without killing the process.
    term = _FakeTerminal()
    prev = signal.getsignal(signal.SIGTERM)
    guards = install_terminal_guards(term, atexit_mod=_FakeAtexit())
    try:
        assert signal.getsignal(signal.SIGTERM) is guards.handler
    finally:
        guards.uninstall()
    assert signal.getsignal(signal.SIGTERM) == prev


# -- Bug 4: the program honours the terminal's detected depth -----------------

class _DepthTerminal(_FakeTerminal):
    def __init__(self, depth):
        super().__init__()
        self.depth = depth

    def wake(self):
        pass


def test_program_uses_terminal_depth():
    prog = Program(_DepthTerminal(DEPTH_256))
    assert prog.screen.depth == DEPTH_256


def test_program_defaults_to_true_without_depth_attr():
    # HeadlessTerminal exposes no depth -> getattr fallback keeps truecolor.
    from py_tvision.platform.headless import HeadlessTerminal
    prog = Program(HeadlessTerminal(40, 10))
    assert prog.screen.depth == DEPTH_TRUE
