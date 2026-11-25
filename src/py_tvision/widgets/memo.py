# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Multi-line text editor (like an HTML ``<textarea>``).

The text is kept as a list of lines. A visible window of the buffer is drawn;
the caret moves with the arrows, Home/End, PgUp/PgDn; printable keys insert,
Enter splits a line, Backspace/Delete join or remove. The view scrolls both
vertically and horizontally and can drive the existing ``ScrollBar``. A total
``max_length`` caps the text. The value is the whole text (``value``). Colours
use the ``input`` theme roles.
"""

from __future__ import annotations

from ..events import Event, EventKind, Mod
from ..geometry import Point, Rect
from ..screen import DrawContext
from ..text import cut_to_width, str_width
from ..views import Option, State, View
from .scrollbar import ScrollBar


class Memo(View):
    def __init__(self, bounds: Rect, text: str = "", max_length: int = 65535,
                 vscrollbar: ScrollBar | None = None,
                 hscrollbar: ScrollBar | None = None):
        super().__init__(bounds)
        self.max_length = max_length
        self.vscrollbar = vscrollbar
        self.hscrollbar = hscrollbar
        self.lines: list[str] = text.split("\n") if text else [""]
        self.row = 0  # caret line index
        self.col = 0  # caret column (character index into the line)
        self.top = 0  # first visible line
        self.left = 0  # first visible column
        self.options |= Option.SELECTABLE | Option.FIRST_CLICK
        self._sync_scrollbars()

    # -- value --------------------------------------------------------------

    @property
    def value(self) -> str:
        return "\n".join(self.lines)

    @value.setter
    def value(self, text: str) -> None:
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self.lines = text.split("\n") if text else [""]
        self.row = min(self.row, len(self.lines) - 1)
        self.col = min(self.col, len(self.lines[self.row]))
        self.top = 0
        self.left = 0
        self._scroll_into_view()
        self.draw_view()

    def _length(self) -> int:
        # Total characters plus the newlines between lines.
        return sum(len(line) for line in self.lines) + (len(self.lines) - 1)

    # -- geometry -----------------------------------------------------------

    @property
    def view_width(self) -> int:
        return max(1, self.bounds.width)

    @property
    def view_height(self) -> int:
        return max(1, self.bounds.height)

    def _sync_scrollbars(self) -> None:
        if self.vscrollbar is not None:
            self.vscrollbar.set_params(
                self.top, max(0, len(self.lines) - self.view_height), self.view_height)
        if self.hscrollbar is not None:
            longest = max((str_width(line) for line in self.lines), default=0)
            self.hscrollbar.set_params(
                self.left, max(0, longest - self.view_width), self.view_width)

    def _scroll_into_view(self) -> None:
        h, w = self.view_height, self.view_width
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + h:
            self.top = self.row - h + 1
        self.top = max(0, min(self.top, max(0, len(self.lines) - h)))
        line = self.lines[self.row]
        if self.col < self.left:
            self.left = self.col
        while str_width(line[self.left:self.col]) >= w:
            self.left += 1
        self.left = max(0, self.left)
        self._sync_scrollbars()

    # -- editing ------------------------------------------------------------

    def _insert_text(self, text: str) -> None:
        """Insert ``text`` at the caret in one splice.

        Line breaks are normalised first (a bracketed paste from xterm sends
        CR, Windows text CRLF). The insert is cut to the room left under
        ``max_length`` (a line break counts as one character, as in
        :meth:`_length`), then split into lines and spliced in at once, so a
        large paste costs time linear in its size.
        """
        if "\r" in text:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        room = self.max_length - self._length()
        if room <= 0 or not text:
            return
        text = text[:room]
        parts = text.split("\n")
        line = self.lines[self.row]
        head, tail = line[:self.col], line[self.col:]
        if len(parts) == 1:
            self.lines[self.row] = head + text + tail
            self.col += len(text)
            return
        new = [head + parts[0], *parts[1:-1], parts[-1] + tail]
        self.lines[self.row:self.row + 1] = new
        self.row += len(parts) - 1
        self.col = len(parts[-1])

    def _newline(self) -> None:
        if self._length() >= self.max_length:
            return
        line = self.lines[self.row]
        self.lines[self.row] = line[:self.col]
        self.lines.insert(self.row + 1, line[self.col:])
        self.row += 1
        self.col = 0

    def _backspace(self) -> None:
        if self.col > 0:
            line = self.lines[self.row]
            self.lines[self.row] = line[:self.col - 1] + line[self.col:]
            self.col -= 1
        elif self.row > 0:
            prev = self.lines[self.row - 1]
            self.col = len(prev)
            self.lines[self.row - 1] = prev + self.lines[self.row]
            del self.lines[self.row]
            self.row -= 1

    def _delete(self) -> None:
        line = self.lines[self.row]
        if self.col < len(line):
            self.lines[self.row] = line[:self.col] + line[self.col + 1:]
        elif self.row < len(self.lines) - 1:
            self.lines[self.row] = line + self.lines[self.row + 1]
            del self.lines[self.row + 1]

    # -- caret movement -----------------------------------------------------

    def _left(self) -> None:
        if self.col > 0:
            self.col -= 1
        elif self.row > 0:
            self.row -= 1
            self.col = len(self.lines[self.row])

    def _right(self) -> None:
        if self.col < len(self.lines[self.row]):
            self.col += 1
        elif self.row < len(self.lines) - 1:
            self.row += 1
            self.col = 0

    def _vertical(self, delta: int) -> None:
        self.row = max(0, min(len(self.lines) - 1, self.row + delta))
        self.col = min(self.col, len(self.lines[self.row]))

    # -- drawing ------------------------------------------------------------

    def draw(self, ctx: DrawContext) -> None:
        focused = bool(self.state & State.FOCUSED)
        base = self.get_style("input.focused" if focused else "input")
        w, h = self.view_width, self.view_height
        ctx.fill(Rect(0, 0, w, h), " ", base)
        for r in range(h):
            li = self.top + r
            if li >= len(self.lines):
                break
            visible = cut_to_width(self.lines[li][self.left:], w)
            ctx.write_text(0, r, visible, base)
        if focused:
            cy = self.row - self.top
            cx = str_width(self.lines[self.row][self.left:self.col])
            if 0 <= cy < h:
                self.cursor = Point(min(cx, w - 1), cy)
            else:
                self.cursor = None
        else:
            self.cursor = None

    # -- events -------------------------------------------------------------

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.PASTE:
            self._insert_text(ev.text)
            self._scroll_into_view()
            self.draw_view()
            ev.clear()
            return
        if ev.kind == EventKind.MOUSE_DOWN and self.abs_bounds().contains(ev.mouse):
            o = self.abs_origin()
            self.row = max(0, min(len(self.lines) - 1, self.top + (ev.mouse.y - o.y)))
            self.col = min(len(self.lines[self.row]), self.left + (ev.mouse.x - o.x))
            self._scroll_into_view()
            self.draw_view()
            ev.clear()
            return
        if ev.kind != EventKind.KEY:
            return
        handled = True
        if ev.key == "Left" and ev.mods == Mod.NONE:
            self._left()
        elif ev.key == "Right" and ev.mods == Mod.NONE:
            self._right()
        elif ev.key == "Up" and ev.mods == Mod.NONE:
            self._vertical(-1)
        elif ev.key == "Down" and ev.mods == Mod.NONE:
            self._vertical(1)
        elif ev.key == "Home":
            self.col = 0
        elif ev.key == "End":
            self.col = len(self.lines[self.row])
        elif ev.key == "PageUp":
            self._vertical(-self.view_height)
        elif ev.key == "PageDown":
            self._vertical(self.view_height)
        elif ev.key == "Enter" and ev.mods == Mod.NONE:
            self._newline()
        elif ev.key == "Backspace":
            self._backspace()
        elif ev.key == "Delete":
            self._delete()
        elif ev.text and not (ev.mods & (Mod.CTRL | Mod.ALT)) and ev.text >= " ":
            self._insert_text(ev.text)
        else:
            handled = False
        if handled:
            self._scroll_into_view()
            self.draw_view()
            ev.clear()
