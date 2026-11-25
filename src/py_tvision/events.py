# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Events, keys, modifiers and commands.

Keys are carried by *name* (``"Enter"``, ``"F1"``, ``"A"``, ``"Up"``) plus a
modifier bitmask, never as packed scan codes, so tables read naturally and
Alt-letter works regardless of keyboard layout. Commands are integers; the
standard set is an ``IntEnum`` and applications add their own at
``CMD_USER`` (1000) and above.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Any, Callable

from .geometry import Point


class Mod(IntFlag):
    NONE = 0
    SHIFT = 1
    CTRL = 2
    ALT = 4


class EventKind(IntEnum):
    NOTHING = 0
    KEY = 1
    MOUSE_DOWN = 2
    MOUSE_UP = 3
    MOUSE_MOVE = 4
    MOUSE_WHEEL = 5
    COMMAND = 6
    BROADCAST = 7
    PASTE = 8
    RESIZE = 9


# Mouse button bits.
MB_LEFT = 1
MB_RIGHT = 2
MB_MIDDLE = 4


class Command(IntEnum):
    NONE = 0
    OK = 1
    CANCEL = 2
    QUIT = 3
    YES = 4
    NO = 5
    MENU = 6
    CLOSE = 7
    NEXT = 8
    PREV = 9


CMD_USER = 1000  # application commands start here


@dataclass
class Event:
    kind: EventKind = EventKind.NOTHING
    key: str = ""
    mods: Mod = Mod.NONE
    text: str = ""
    mouse: Point = field(default_factory=Point)
    buttons: int = 0
    wheel: int = 0  # +1 up, -1 down
    command: int = 0
    info: Any = None
    _handled: bool = False

    def clear(self) -> None:
        """Mark the event handled (routing stops bubbling it)."""
        self._handled = True
        self.kind = EventKind.NOTHING

    @property
    def handled(self) -> bool:
        return self._handled or self.kind == EventKind.NOTHING

    # Convenience predicates ------------------------------------------------

    def is_key(self, name: str, mods: Mod = Mod.NONE) -> bool:
        return self.kind == EventKind.KEY and self.key == name and self.mods == mods

    def is_command(self, cmd: int) -> bool:
        return self.kind in (EventKind.COMMAND, EventKind.BROADCAST) and self.command == cmd


# --- Constructors ----------------------------------------------------------

def key_event(name: str, mods: Mod = Mod.NONE, text: str = "") -> Event:
    return Event(kind=EventKind.KEY, key=name, mods=mods, text=text)


def command_event(cmd: int, info: Any = None) -> Event:
    return Event(kind=EventKind.COMMAND, command=cmd, info=info)


def broadcast_event(cmd: int, info: Any = None) -> Event:
    return Event(kind=EventKind.BROADCAST, command=cmd, info=info)


def mouse_event(kind: EventKind, x: int, y: int, buttons: int = 0, wheel: int = 0,
                mods: Mod = Mod.NONE) -> Event:
    return Event(kind=kind, mouse=Point(x, y), buttons=buttons, wheel=wheel, mods=mods)


def paste_event(text: str) -> Event:
    return Event(kind=EventKind.PASTE, text=text)


def resize_event(width: int, height: int) -> Event:
    return Event(kind=EventKind.RESIZE, info=(width, height))


# --- Key-name parsing helper ----------------------------------------------

def key_spec(spec: str) -> tuple[str, Mod]:
    """Parse ``"Alt+Q"`` / ``"Ctrl+Enter"`` into ``(name, mods)``."""
    parts = spec.split("+")
    name = parts[-1]
    mods = Mod.NONE
    for p in parts[:-1]:
        pl = p.strip().lower()
        if pl == "alt":
            mods |= Mod.ALT
        elif pl == "ctrl":
            mods |= Mod.CTRL
        elif pl == "shift":
            mods |= Mod.SHIFT
    return name, mods


# --- Thread-safe post queue ------------------------------------------------

class PostQueue:
    """A queue a worker thread uses to hand work to the UI thread.

    Items are either ready-made ``Event`` objects or zero-argument callables
    (run on the UI thread). ``wake`` is invoked after every put so the
    platform loop can break out of its wait.
    """

    def __init__(self, wake: Callable[[], None] | None = None):
        self._q: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._wake = wake
        self._lock = threading.Lock()

    def set_wake(self, wake: Callable[[], None]) -> None:
        with self._lock:
            self._wake = wake

    def post(self, item: Event | Callable[[], None]) -> None:
        self._q.put(item)
        with self._lock:
            wake = self._wake
        if wake is not None:
            wake()

    def drain(self) -> list[Any]:
        out: list[Any] = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

    def empty(self) -> bool:
        return self._q.empty()
