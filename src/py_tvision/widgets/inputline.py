# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Single-line text input with horizontal scrolling and a simple selection."""

from __future__ import annotations

from ..events import Event, EventKind, Mod
from ..geometry import Point, Rect
from ..screen import DrawContext
from ..text import cut_to_width, str_width
from ..views import Option, State, View


class InputLine(View):
    def __init__(self, bounds: Rect, max_length: int = 255, text: str = "",
                 password: bool = False, mask: str = "•"):
        super().__init__(bounds)
        self.data = text
        self.max_length = max_length
        self.password = password
        self.mask = mask
        self.cursor_pos = len(text)  # index into data (characters)
        self.first = 0  # first visible character index
        self.sel_anchor: int | None = None
        self.options |= Option.SELECTABLE | Option.FIRST_CLICK

    def __repr__(self) -> str:
        # Never leak the secret in a debug string or a traceback.
        if self.password:
            return f"{type(self).__name__}(password, length={len(self.data)})"
        return f"{type(self).__name__}(data={self.data!r})"

    def _shown(self) -> str:
        """The string as drawn: the real data, or a mask in password mode."""
        return self.mask * len(self.data) if self.password else self.data

    # -- helpers ------------------------------------------------------------

    def _width(self) -> int:
        return max(1, self.bounds.width)

    def _selection(self) -> tuple[int, int] | None:
        if self.sel_anchor is None or self.sel_anchor == self.cursor_pos:
            return None
        a, b = sorted((self.sel_anchor, self.cursor_pos))
        return a, b

    def selected_text(self) -> str:
        sel = self._selection()
        if sel is None:
            return ""
        return self.data[sel[0]:sel[1]]

    def _delete_selection(self) -> bool:
        sel = self._selection()
        if sel is None:
            return False
        self.data = self.data[:sel[0]] + self.data[sel[1]:]
        self.cursor_pos = sel[0]
        self.sel_anchor = None
        return True

    def _scroll_into_view(self) -> None:
        if self.cursor_pos < self.first:
            self.first = self.cursor_pos
        width = self._width()
        # Advance first until the caret is visible.
        while str_width(self.data[self.first:self.cursor_pos]) >= width:
            self.first += 1

    def insert(self, text: str) -> None:
        self._delete_selection()
        room = self.max_length - len(self.data)
        if room <= 0:
            return
        text = text[:room]
        self.data = self.data[:self.cursor_pos] + text + self.data[self.cursor_pos:]
        self.cursor_pos += len(text)
        self._scroll_into_view()
        self.draw_view()

    # -- drawing ------------------------------------------------------------

    def draw(self, ctx: DrawContext) -> None:
        focused = bool(self.state & State.FOCUSED)
        base = self.get_style("input.focused" if focused else "input")
        sel_style = self.get_style("input.selected")
        width = self._width()
        ctx.fill(Rect(0, 0, width, 1), " ", base)

        shown = self._shown()
        visible = cut_to_width(shown[self.first:], width)
        sel = self._selection()
        col = 0
        for i, ch in enumerate(visible):
            idx = self.first + i
            style = sel_style if (sel and sel[0] <= idx < sel[1]) else base
            ctx.write_text(col, 0, ch, style)
            col += str_width(ch)

        if focused:
            caret = str_width(shown[self.first:self.cursor_pos])
            self.cursor = Point(min(caret, width - 1), 0)
        else:
            self.cursor = None

    # -- events -------------------------------------------------------------

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.PASTE:
            self.insert(ev.text.replace("\n", " "))
            ev.clear()
            return
        if ev.kind == EventKind.MOUSE_DOWN and self.abs_bounds().contains(ev.mouse):
            ox = self.abs_origin().x
            target = ev.mouse.x - ox + self.first
            self.cursor_pos = max(0, min(len(self.data), target))
            self.sel_anchor = None
            self._scroll_into_view()
            ev.clear()
            return
        if ev.kind != EventKind.KEY:
            return
        shift = bool(ev.mods & Mod.SHIFT)
        if ev.mods & Mod.CTRL and ev.key in ("C", "V", "X"):
            self._clipboard_key(ev.key)
            ev.clear()
            return
        handled = True
        if ev.key == "Left" and ev.mods in (Mod.NONE, Mod.SHIFT):
            self._move(self.cursor_pos - 1, shift)
        elif ev.key == "Right" and ev.mods in (Mod.NONE, Mod.SHIFT):
            self._move(self.cursor_pos + 1, shift)
        elif ev.key == "Home":
            self._move(0, shift)
        elif ev.key == "End":
            self._move(len(self.data), shift)
        elif ev.key == "Backspace":
            if not self._delete_selection() and self.cursor_pos > 0:
                self.data = self.data[:self.cursor_pos - 1] + self.data[self.cursor_pos:]
                self.cursor_pos -= 1
        elif ev.key == "Delete":
            if not self._delete_selection() and self.cursor_pos < len(self.data):
                self.data = self.data[:self.cursor_pos] + self.data[self.cursor_pos + 1:]
        elif ev.text and len(ev.text) >= 1 and not (ev.mods & (Mod.CTRL | Mod.ALT)) and ev.text >= " ":
            self.insert(ev.text)
        else:
            handled = False
        if handled:
            self._scroll_into_view()
            self.draw_view()
            ev.clear()

    def _move(self, new_pos: int, extend: bool) -> None:
        new_pos = max(0, min(len(self.data), new_pos))
        if extend:
            if self.sel_anchor is None:
                self.sel_anchor = self.cursor_pos
        else:
            self.sel_anchor = None
        self.cursor_pos = new_pos

    def _clipboard_key(self, key: str) -> None:
        prog = self.program()
        if self.password and key in ("C", "X"):
            # A password must never reach the clipboard; copy/cut are inert.
            # Paste stays allowed (e.g. from a password manager).
            return
        if key in ("C", "X"):
            text = self.selected_text() or self.data
            setter = getattr(prog, "set_clipboard", None)
            if setter is not None:
                setter(text)
            if key == "X":
                self._delete_selection()
                self.draw_view()
        elif key == "V":
            getter = getattr(prog, "get_clipboard", None)
            if getter is not None:
                self.insert((getter() or "").replace("\n", " "))
