# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""List box with a focused item, scrolling and an optional linked scroll bar."""

from __future__ import annotations

from ..events import Command, Event, EventKind, Mod
from ..geometry import Rect
from ..screen import DrawContext
from ..text import cut_to_width
from ..views import Option, State, View
from .scrollbar import ScrollBar


class ListBox(View):
    def __init__(self, bounds: Rect, items: list[str] | None = None,
                 scrollbar: ScrollBar | None = None):
        super().__init__(bounds)
        self.items: list[str] = list(items) if items else []
        self.focused_index = 0
        self.top = 0
        self.scrollbar = scrollbar
        self.options |= Option.SELECTABLE | Option.FIRST_CLICK
        self._sync_scrollbar()

    def set_items(self, items: list[str]) -> None:
        self.items = list(items)
        self.focused_index = 0
        self.top = 0
        self._sync_scrollbar()
        self.draw_view()

    @property
    def visible_rows(self) -> int:
        return max(1, self.bounds.height)

    def focused_item(self) -> str | None:
        if 0 <= self.focused_index < len(self.items):
            return self.items[self.focused_index]
        return None

    def _sync_scrollbar(self) -> None:
        if self.scrollbar is not None:
            self.scrollbar.set_params(self.top, max(0, len(self.items) - self.visible_rows),
                                      self.visible_rows)

    def _scroll_into_view(self) -> None:
        if self.focused_index < self.top:
            self.top = self.focused_index
        elif self.focused_index >= self.top + self.visible_rows:
            self.top = self.focused_index - self.visible_rows + 1
        self.top = max(0, min(self.top, max(0, len(self.items) - self.visible_rows)))
        self._sync_scrollbar()

    def draw_item(self, ctx: DrawContext, row: int, index: int, text: str, style) -> None:
        """Override to colour items; default writes the padded text."""
        ctx.write_text(0, row, cut_to_width(text, self.bounds.width), style)

    def draw(self, ctx: DrawContext) -> None:
        focused_widget = bool(self.state & State.FOCUSED)
        base = self.get_style("list")
        sel = self.get_style("list.focused" if focused_widget else "list.selected")
        w, h = self.bounds.width, self.bounds.height
        ctx.fill(Rect(0, 0, w, h), " ", base)
        for row in range(h):
            index = self.top + row
            if index >= len(self.items):
                break
            style = sel if index == self.focused_index else base
            if index == self.focused_index:
                ctx.fill(Rect(0, row, w, row + 1), " ", style)
            self.draw_item(ctx, row, index, self.items[index], style)

    def _move(self, new_index: int) -> None:
        if not self.items:
            return
        self.focused_index = max(0, min(len(self.items) - 1, new_index))
        self._scroll_into_view()
        self.draw_view()

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.KEY and ev.mods == Mod.NONE:
            key = ev.key
            if key == "Up":
                self._move(self.focused_index - 1)
            elif key == "Down":
                self._move(self.focused_index + 1)
            elif key == "PageUp":
                self._move(self.focused_index - self.visible_rows)
            elif key == "PageDown":
                self._move(self.focused_index + self.visible_rows)
            elif key == "Home":
                self._move(0)
            elif key == "End":
                self._move(len(self.items) - 1)
            elif key == "Enter":
                self.emit_command(Command.OK)
            else:
                return
            ev.clear()
        elif ev.kind == EventKind.MOUSE_DOWN and self.abs_bounds().contains(ev.mouse):
            oy = self.abs_origin().y
            self._move(self.top + (ev.mouse.y - oy))
            ev.clear()
        elif ev.kind == EventKind.MOUSE_WHEEL and self.abs_bounds().contains(ev.mouse):
            self._move(self.focused_index + (-1 if ev.wheel > 0 else 1))
            ev.clear()
