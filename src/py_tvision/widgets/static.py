# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Static text and labels."""

from __future__ import annotations

from ..events import Event, EventKind, Mod
from ..geometry import Rect
from ..screen import DrawContext
from ..text import parse_hotkey
from ..views import Option, State, View


class StaticText(View):
    """Non-interactive text, one or more lines (split on ``\\n``)."""

    def __init__(self, bounds: Rect, text: str, role: str = "static"):
        super().__init__(bounds)
        self.text = text
        self.role = role

    def draw(self, ctx: DrawContext) -> None:
        style = self.get_style(self.role)
        ctx.fill(Rect(0, 0, self.bounds.width, self.bounds.height), " ", style)
        for i, line in enumerate(self.text.split("\n")):
            if i >= self.bounds.height:
                break
            ctx.write_text(0, i, line, style)


class Label(View):
    """A caption with a ``~X~`` hotkey that focuses a linked view."""

    def __init__(self, bounds: Rect, text: str, link: View | None = None):
        super().__init__(bounds)
        self.display, self.hotkey, self.hot_index = parse_hotkey(text)
        self.link = link
        self.options |= Option.PRE_PROCESS  # see Alt-hotkey before focus chain

    def draw(self, ctx: DrawContext) -> None:
        base = self.get_style("label")
        hot = self.get_style("label.hotkey")
        ctx.fill(Rect(0, 0, self.bounds.width, self.bounds.height), " ", base)
        ctx.write_text(0, 0, self.display, base)
        if self.hotkey is not None and 0 <= self.hot_index < self.bounds.width:
            ch = self.display[self.hot_index] if self.hot_index < len(self.display) else ""
            if ch:
                ctx.put(self.hot_index, 0, ch, hot)

    def handle_event(self, ev: Event) -> None:
        if (self.link is not None and self.hotkey is not None
                and ev.kind == EventKind.KEY and ev.mods & Mod.ALT
                and ev.key == self.hotkey):
            self.link.focus()
            ev.clear()
        elif (self.link is not None and ev.kind == EventKind.MOUSE_DOWN
              and self.abs_bounds().contains(ev.mouse)):
            self.link.focus()
            ev.clear()
