# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""POSIX terminal backend (termios + select).

Raw mode on ``/dev/tty`` (or stdin), the alternate screen, SGR mouse and
bracketed paste; input bytes go through the shared :class:`VTInputDecoder`.
A ``SIGWINCH`` self-pipe turns resizes into events and ``wake()`` writes the
same pipe so a worker thread can break a blocked ``select``. A lone ESC is
promoted to an ``Esc`` key only once a fixed deadline (50 ms after the last
byte of the pending sequence) has passed; a wake or a short app timer only
shortens one wait and never flushes a sequence early.

Parts follow ideas in magiblot/tvision's ``termio.cpp``/``sigwinch.cpp``
(Copyright 2019-2025 magiblot, MIT); no code is translated.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable

from ..color import detect_depth
from ..events import Event, resize_event
from .vtinput import VTInputDecoder

_ESC_TIMEOUT = 0.05  # seconds to wait before a lone ESC becomes an Esc key


def resolve_pending_escape(decoder: VTInputDecoder,
                           read_more: Callable[[], bytes]) -> list[Event]:
    """Decide a buffered lone ``ESC`` versus a continuing CSI/SS3/Alt sequence.

    ``decoder`` must have a pending escape (see
    :meth:`VTInputDecoder.pending_escape`). ``read_more`` is called exactly once
    and returns whatever continuation bytes arrived within the escape timeout,
    or ``b""`` on timeout. With bytes we feed them (completing the sequence or
    forming ``Alt+key``); on timeout we flush the pending ESC to an ``Esc`` key.

    The decision is pure with respect to ``read_more``, so tests drive it with a
    fake instead of a real ``select``. :meth:`PosixTerminal.read` itself uses
    the deadline logic (``_escape_wait``/``_flush_if_due``) instead, because a
    ``select`` that returns without tty bytes is not proof the timeout passed.
    """
    data = read_more()
    if data:
        return decoder.feed(data)
    return decoder.flush()


class PosixTerminal:
    is_headless = False

    def __init__(self) -> None:
        if sys.platform == "win32":
            raise RuntimeError("PosixTerminal is not available on Windows")
        import select
        import termios
        import tty

        self._select = select
        self._termios = termios
        self._tty = tty
        try:
            self._fd = os.open("/dev/tty", os.O_RDWR)
            self._own_fd = True
        except OSError:
            self._fd = sys.stdin.fileno()
            self._own_fd = False
        self._wake_r, self._wake_w = os.pipe()
        os.set_blocking(self._wake_r, False)
        self._decoder = VTInputDecoder()
        self._clock: Callable[[], float] = time.monotonic  # injectable for tests
        self._esc_deadline: float | None = None
        self._old_attrs = None
        self._started = False
        self.depth = detect_depth()

    def start(self) -> None:
        import signal

        self._old_attrs = self._termios.tcgetattr(self._fd)
        self._tty.setraw(self._fd)
        self.write("\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1002h\x1b[?1006h\x1b[?2004h")
        try:
            signal.signal(signal.SIGWINCH, self._on_winch)
        except (ValueError, OSError):
            pass  # not in the main thread
        self._started = True

    def _on_winch(self, *_a) -> None:
        try:
            os.write(self._wake_w, b"W")
        except OSError:
            pass

    def stop(self) -> None:
        if self._started:
            self.write("\x1b[?2004l\x1b[?1006l\x1b[?1002l\x1b[?1000l\x1b[?25h\x1b[?1049l")
        self._started = False
        if self._old_attrs is not None:
            attrs, self._old_attrs = self._old_attrs, None  # idempotent
            self._termios.tcsetattr(self._fd, self._termios.TCSANOW, attrs)

    def size(self) -> tuple[int, int]:
        try:
            sz = os.get_terminal_size(self._fd)
            return max(1, sz.columns), max(1, sz.lines)
        except OSError:
            return 80, 25

    def _escape_wait(self, timeout: float | None) -> float | None:
        """Bound ``timeout`` by the pending-escape deadline, if any.

        When an ``ESC``-prefixed sequence is buffered, its deadline is set the
        first time we see it (``now + _ESC_TIMEOUT``); later waits only use what
        is left of it. With nothing pending the deadline is cleared and the
        caller's timeout is returned unchanged.
        """
        if not self._decoder.pending_escape():
            self._esc_deadline = None
            return timeout
        now = self._clock()
        if self._esc_deadline is None:
            self._esc_deadline = now + _ESC_TIMEOUT
        remaining = max(0.0, self._esc_deadline - now)
        return remaining if timeout is None else min(timeout, remaining)

    def _feed(self, data: bytes) -> list[Event]:
        """Feed tty bytes; new bytes restart the deadline of a pending escape."""
        events = self._decoder.feed(data)
        if self._decoder.pending_escape():
            self._esc_deadline = self._clock() + _ESC_TIMEOUT
        else:
            self._esc_deadline = None
        return events

    def _flush_if_due(self) -> list[Event]:
        """Turn a still-pending escape into ``Esc`` once its deadline passed.

        This is the only place a partial sequence is flushed. A ``select`` that
        returned early (wake pipe, SIGWINCH, a short app timer) leaves the
        buffered bytes alone, so a sequence split across such a wake-up still
        decodes correctly when its tail arrives.
        """
        if self._esc_deadline is None or not self._decoder.pending_escape():
            self._esc_deadline = None
            return []
        if self._clock() < self._esc_deadline:
            return []
        self._esc_deadline = None
        return self._decoder.flush()

    def read(self, timeout: float | None) -> list[Event]:
        # A dangling ESC must resolve on its own schedule, not when the next,
        # unrelated key finally arrives (that would misread it as Alt+key), and
        # not merely because select() returned early for another reason.
        timeout = self._escape_wait(timeout)
        rlist, _, _ = self._select.select([self._fd, self._wake_r], [], [], timeout)
        events: list[Event] = []
        resized = False
        if self._wake_r in rlist:
            try:
                data = os.read(self._wake_r, 4096)
                if b"W" in data:
                    resized = True
            except OSError:
                pass
        if self._fd in rlist:
            try:
                data = os.read(self._fd, 4096)
            except OSError:
                data = b""
            if data:
                events.extend(self._feed(data))
        events.extend(self._flush_if_due())
        if resized:
            w, h = self.size()
            events.append(resize_event(w, h))
        return events

    def write(self, text: str) -> None:
        os.write(self._fd, text.encode("utf-8", "replace"))

    def wake(self) -> None:
        try:
            os.write(self._wake_w, b".")
        except OSError:
            pass

    def set_clipboard(self, text: str) -> None:
        import base64

        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self.write(f"\x1b]52;c;{b64}\x07")
