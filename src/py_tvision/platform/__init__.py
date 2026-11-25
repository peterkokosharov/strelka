# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Platform backends and the common Terminal interface.

A ``Terminal`` hides the console differences behind a small surface:

    start()                 enter raw mode, alt screen, mouse on, hide cursor
    stop()                  restore exactly what start() changed
    size() -> (w, h)        current window size in cells
    read(timeout) -> list   pending events, waiting at most ``timeout`` seconds
    write(text)             send a VT string for one frame
    wake()                  break a blocked read() from another thread
    set_clipboard(text)     best-effort system clipboard
    is_headless             True for the in-memory test terminal
"""

from __future__ import annotations

import sys
from typing import Protocol

from ..events import Event


class Terminal(Protocol):
    is_headless: bool

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def size(self) -> tuple[int, int]: ...
    def read(self, timeout: float | None) -> list[Event]: ...
    def write(self, text: str) -> None: ...
    def wake(self) -> None: ...
    def set_clipboard(self, text: str) -> None: ...


def open_terminal() -> Terminal:
    """Pick the right real backend for this OS.

    Tests use :class:`py_tvision.platform.headless.HeadlessTerminal` directly
    instead of calling this.
    """
    if sys.platform == "win32":
        from .win32 import Win32Terminal

        return Win32Terminal()
    from .posix import PosixTerminal

    return PosixTerminal()
