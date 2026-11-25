# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Push button."""

from __future__ import annotations

from ..events import Event, EventKind, Mod
from ..geometry import Rect
from ..screen import DrawContext
from ..text import parse_hotkey, str_width
from ..views import Option, State, View


class Button(View):
    def __init__(self, bounds: Rect, text: str, command: int, default: bool = False):
        super().__init__(bounds)
        self.display, self.hotkey, self.hot_index = parse_hotkey(text)
        self.command = command
        self.default = default
        self.options |= Option.SELECTABLE | Option.PRE_PROCESS | Option.FIRST_CLICK

    def draw(self, ctx: DrawContext) -> None:
        focused = bool(self.state & State.FOCUSED)
        disabled = bool(self.state & State.DISABLED)
        if focused:
            face = self.get_style("button.focused")
        elif self.default:
            face = self.get_style("button.default")
        else:
            face = self.get_style("button")
        hot = self.get_style("button.hotkey")
        shadow = self.get_style("button.shadow")
        w = self.bounds.width

        # Button face on row 0.
        ctx.fill(Rect(0, 0, w, 1), " ", face)
        label = self.display
        lw = str_width(label)
        lx = max(1, (w - lw) // 2)
        ctx.write_text(lx, 0, label, face)
        if self.hotkey is not None and not focused and not disabled:
            idx = lx + self.hot_index
            if 0 <= self.hot_index < len(label):
                ctx.put(idx, 0, label[self.hot_index], hot)

        # Half-block shadow: one row below and one column to the right.
        if self.bounds.height > 1:
            ctx.hline(1, 1, w - 1, "▀", shadow)
        ctx.put(w - 1, 0, " ", shadow) if w > 0 else None

    def press(self) -> None:
        if not (self.state & State.DISABLED):
            self.emit_command(self.command)

    def handle_event(self, ev: Event) -> None:
        if self.state & State.DISABLED:
            return
        if ev.kind == EventKind.KEY:
            focused = bool(self.state & State.FOCUSED)
            if focused and ev.key in ("Enter", " ") and ev.mods == Mod.NONE:
                self.press()
                ev.clear()
                return
            if (self.hotkey is not None and ev.mods & Mod.ALT and ev.key == self.hotkey):
                self.press()
                ev.clear()
                return
        elif ev.kind == EventKind.MOUSE_DOWN:
            if self.abs_bounds().contains(ev.mouse):
                self.press()
                ev.clear()
