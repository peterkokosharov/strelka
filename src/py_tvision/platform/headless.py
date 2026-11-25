# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""An in-memory terminal for tests and snapshots.

It never touches a real console: events are queued with :meth:`feed_events`
(or :meth:`feed_bytes`, decoded through the shared VT decoder), ``read``
returns and clears the queue without blocking, and ``write`` accumulates the
VT output so a round-trip test can replay it. ``read`` returns ``[]`` when the
queue is empty, which the application loop treats, in headless mode, as "no
more input" so a modal loop can never hang in a test.
"""

from __future__ import annotations

from ..events import Event, resize_event
from .vtinput import VTInputDecoder


class HeadlessTerminal:
    is_headless = True

    def __init__(self, width: int = 80, height: int = 25):
        self._width = width
        self._height = height
        self._queue: list[Event] = []
        self._decoder = VTInputDecoder()
        self.output: list[str] = []
        self.started = False
        self.stopped = False
        self.clipboard: str | None = None
        self.woken = 0

    # Terminal interface ----------------------------------------------------

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def size(self) -> tuple[int, int]:
        return self._width, self._height

    def read(self, timeout: float | None) -> list[Event]:
        evs = self._queue
        self._queue = []
        return evs

    def write(self, text: str) -> None:
        if text:
            self.output.append(text)

    def wake(self) -> None:
        self.woken += 1

    def set_clipboard(self, text: str) -> None:
        self.clipboard = text

    # Test helpers ----------------------------------------------------------

    def feed_events(self, *events: Event) -> None:
        self._queue.extend(events)

    def feed_bytes(self, data: bytes) -> None:
        self._queue.extend(self._decoder.feed(data))

    def resize(self, width: int, height: int) -> None:
        self._width = width
        self._height = height
        self._queue.append(resize_event(width, height))

    def output_text(self) -> str:
        return "".join(self.output)
