# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Drop-down selection field (like an HTML ``<select>``).

A one-line field shows the chosen item and a ``down`` arrow. Enter or Alt-Down
(or a mouse click) drop a framed ``ListBox`` popup, run as a nested modal
(``exec_view``, the same mechanism as a message box); Enter picks the focused
row and Esc cancels. The value is the chosen index (``index``) or item text
(``value``). Colours use the ``input`` theme roles so it renders in all three
themes.
"""

from __future__ import annotations

from ..events import Command, Event, EventKind, Mod
from ..geometry import Rect
from ..screen import DrawContext
from ..text import ARROW_DOWN, cut_to_width
from ..views import Option, State, View
from ..window import Dialog
from .listbox import ListBox

POPUP_MAX_ROWS = 6


class _ComboPopup(Dialog):
    """A small framed dialog holding the drop-down list."""

    def __init__(self, bounds: Rect, items: list[str], index: int):
        super().__init__(bounds, title="", closeable=False)
        inner = self.interior()
        self.list = ListBox(inner, items)
        self.list.focused_index = max(0, min(index, len(items) - 1)) if items else 0
        self.list._scroll_into_view()
        self.insert(self.list)


class ComboBox(View):
    def __init__(self, bounds: Rect, items: list[str] | None = None, index: int = 0):
        super().__init__(bounds)
        self.items: list[str] = list(items) if items else []
        self.index = index if self.items else -1
        self.options |= Option.SELECTABLE | Option.FIRST_CLICK

    # -- value --------------------------------------------------------------

    def selected_text(self) -> str:
        if 0 <= self.index < len(self.items):
            return self.items[self.index]
        return ""

    @property
    def value(self) -> str:
        return self.selected_text()

    @value.setter
    def value(self, item: str) -> None:
        if item in self.items:
            self.index = self.items.index(item)
            self.draw_view()

    def set_items(self, items: list[str]) -> None:
        self.items = list(items)
        self.index = 0 if self.items else -1
        self.draw_view()

    # -- drawing ------------------------------------------------------------

    def draw(self, ctx: DrawContext) -> None:
        focused = bool(self.state & State.FOCUSED)
        base = self.get_style("input.focused" if focused else "input")
        arrow = self.get_style("input.arrow")
        w = self.bounds.width
        ctx.fill(Rect(0, 0, w, 1), " ", base)
        ctx.write_text(0, 0, cut_to_width(self.selected_text(), max(0, w - 1)), base)
        if w > 0:
            ctx.put(w - 1, 0, ARROW_DOWN, arrow)
        self.cursor = None  # a select has no text caret

    # -- drop down ----------------------------------------------------------

    def open(self) -> None:
        """Run the drop-down popup modally and keep the chosen item."""
        if not self.items:
            return
        prog = self.program()
        desktop = getattr(prog, "desktop", None)
        if prog is None or desktop is None:
            return
        rows = min(len(self.items), POPUP_MAX_ROWS)
        height = rows + 2  # frame top and bottom
        width = max(self.bounds.width, 8)
        o = self.abs_origin()
        do = desktop.abs_origin()
        x = o.x - do.x
        y = o.y - do.y + 1
        # Keep the popup on the desktop; flip above the field if it would overflow.
        if y + height > desktop.bounds.height:
            y = max(0, (o.y - do.y) - height)
        x = max(0, min(x, max(0, desktop.bounds.width - width)))
        popup = _ComboPopup(Rect(x, y, x + width, y + height),
                            self.items, max(0, self.index))
        result = prog.exec_view(popup)
        if result in (Command.OK, Command.YES):
            self.index = popup.list.focused_index
        self.focus()
        self.draw_view()

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.KEY and bool(self.state & State.FOCUSED):
            if ev.key == "Enter" and ev.mods == Mod.NONE:
                self.open()
                ev.clear()
                return
            if ev.key == "Down" and ev.mods & Mod.ALT:
                self.open()
                ev.clear()
                return
        elif ev.kind == EventKind.MOUSE_DOWN and self.abs_bounds().contains(ev.mouse):
            self.open()
            ev.clear()
