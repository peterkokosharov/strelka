# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""py_tvision - a small, standard-library text-UI toolkit.

Independent design inspired by Turbo Vision (see
``docs/PY_TVISION_DESIGN.md``); it is not a translation of Borland-origin
tvision code. Phase 1 provides the screen buffer with diffing, the view/group
model, windows and dialogs, the event loop, cross-platform rendering and
input, and the core widgets needed by a runnable demo.
"""

from __future__ import annotations

from .app import Application, Desktop, Program
from .events import (
    CMD_USER,
    Command,
    Event,
    EventKind,
    Mod,
    broadcast_event,
    command_event,
    key_event,
    key_spec,
    mouse_event,
    paste_event,
    resize_event,
)
from .geometry import Point, Rect
from .screen import Buffer, DrawContext, Screen
from .theme import Style, Theme, get_theme
from .views import Grow, Group, Option, State, View
from .window import Dialog, Window

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Point", "Rect",
    "Style", "Theme", "get_theme",
    "Buffer", "DrawContext", "Screen",
    "Event", "EventKind", "Mod", "Command", "CMD_USER",
    "key_event", "command_event", "broadcast_event", "mouse_event",
    "paste_event", "resize_event", "key_spec",
    "View", "Group", "State", "Option", "Grow",
    "Window", "Dialog",
    "Program", "Application", "Desktop",
]
