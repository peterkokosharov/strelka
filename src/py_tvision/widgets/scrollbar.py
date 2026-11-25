# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Scroll bar, usually linked to a list view."""

from __future__ import annotations

from ..events import Event, EventKind
from ..geometry import Rect
from ..screen import DrawContext
from ..text import ARROW_DOWN, ARROW_RIGHT, ARROW_LEFT, ARROW_UP, SHADE_LIGHT, SHADE_MEDIUM
from ..views import View


class ScrollBar(View):
    VERTICAL = "v"
    HORIZONTAL = "h"

    def __init__(self, bounds: Rect, orientation: str = VERTICAL):
        super().__init__(bounds)
        self.orientation = orientation
        self.value = 0
        self.max_value = 0
        self.page_step = 1

    def set_params(self, value: int, max_value: int, page_step: int = 1) -> None:
        self.max_value = max(0, max_value)
        self.value = max(0, min(value, self.max_value))
        self.page_step = max(1, page_step)
        self.draw_view()

    def _thumb_pos(self, track_len: int) -> int:
        if self.max_value <= 0 or track_len <= 0:
            return 0
        return round(self.value / self.max_value * (track_len - 1))

    def draw(self, ctx: DrawContext) -> None:
        track = self.get_style("scrollbar")
        arrow = self.get_style("scrollbar.arrow")
        if self.orientation == self.VERTICAL:
            h = self.bounds.height
            ctx.put(0, 0, ARROW_UP, arrow)
            ctx.put(0, h - 1, ARROW_DOWN, arrow)
            track_len = h - 2
            for i in range(track_len):
                ctx.put(0, 1 + i, SHADE_LIGHT, track)
            if track_len > 0:
                ctx.put(0, 1 + self._thumb_pos(track_len), SHADE_MEDIUM, arrow)
        else:
            w = self.bounds.width
            ctx.put(0, 0, ARROW_LEFT, arrow)
            ctx.put(w - 1, 0, ARROW_RIGHT, arrow)
            track_len = w - 2
            for i in range(track_len):
                ctx.put(1 + i, 0, SHADE_LIGHT, track)
            if track_len > 0:
                ctx.put(1 + self._thumb_pos(track_len), 0, SHADE_MEDIUM, arrow)

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.MOUSE_DOWN and self.abs_bounds().contains(ev.mouse):
            o = self.abs_origin()
            if self.orientation == self.VERTICAL:
                if ev.mouse.y == o.y:
                    self.set_params(self.value - 1, self.max_value, self.page_step)
                elif ev.mouse.y == o.y + self.bounds.height - 1:
                    self.set_params(self.value + 1, self.max_value, self.page_step)
            ev.clear()
