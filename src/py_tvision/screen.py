# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""The off-screen buffer, the per-view draw context, and the diff/flush.

Each row keeps two parallel lists, ``chars`` (one string per column, ``""``
for the right half of a wide character) and ``styles`` (one ``Style`` per
column). Views draw into the *back* buffer through a clipped ``DrawContext``;
``flush`` compares back against *front* row by row and emits only the changed
runs as VT escapes, then makes front equal back. Comparing whole rows with a
plain ``==`` is fast and lets untouched rows be skipped entirely.
"""

from __future__ import annotations

from .color import DEPTH_TRUE, sgr
from .geometry import Point, Rect
from .text import char_width, safe_glyph
from .theme import DEFAULT_STYLE, Style


class Buffer:
    """A grid of character cells with styles."""

    def __init__(self, width: int, height: int, style: Style = DEFAULT_STYLE):
        self.width = width
        self.height = height
        self.default_style = style
        self.chars: list[list[str]] = []
        self.styles: list[list[Style]] = []
        self.clear()

    def clear(self, style: Style | None = None) -> None:
        style = self.default_style if style is None else style
        self.chars = [[" "] * self.width for _ in range(self.height)]
        self.styles = [[style] * self.width for _ in range(self.height)]

    def resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.clear()

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def set_cell(self, x: int, y: int, ch: str, style: Style) -> None:
        """Write a single glyph at ``(x, y)``, keeping wide cells consistent."""
        if not (0 <= y < self.height):
            return
        # Sanitise before anything else: untrusted model/tool/file text reaches
        # the terminal only through here, so neutralise any control character
        # (C0/ESC, DEL, C1) that could drive the VT. "" is the right half of a
        # wide cell and must pass through untouched.
        if ch:
            ch = safe_glyph(ch)
        w = char_width(ch) if ch else 1
        if w == 0:
            return  # combining mark: ignore at the buffer level
        if not (0 <= x < self.width):
            return
        row_c = self.chars[y]
        row_s = self.styles[y]
        # If we are overwriting the right half of an existing wide char, blank
        # its orphaned left half.
        if row_c[x] == "" and x > 0:
            row_c[x - 1] = " "
            row_s[x - 1] = style
        # If the cell currently holds a wide char, blank its orphaned right half.
        if x + 1 < self.width and char_width(row_c[x]) == 2 and row_c[x + 1] == "":
            row_c[x + 1] = " "
            row_s[x + 1] = style
        if w == 2:
            if x + 1 >= self.width:
                # No room for the right half: show a space instead of half a glyph.
                row_c[x] = " "
                row_s[x] = style
                return
            # Blank a wide char we are about to clobber on the right.
            if char_width(row_c[x + 1]) == 2 and x + 2 < self.width:
                self.chars[y][x + 2] = " " if self.chars[y][x + 2] == "" else self.chars[y][x + 2]
            row_c[x] = ch
            row_s[x] = style
            row_c[x + 1] = ""
            row_s[x + 1] = style
        else:
            row_c[x] = ch
            row_s[x] = style

    def row_text(self, y: int) -> str:
        """Visual text of a row (wide chars once, right halves dropped)."""
        if not (0 <= y < self.height):
            return ""
        return "".join(c if c != "" else "" for c in self.chars[y])

    def snapshot(self) -> list[str]:
        """Every row as a visual string (for text snapshot tests)."""
        return [self.row_text(y) for y in range(self.height)]

    def snapshot_styles(self) -> tuple[list[str], dict[str, Style]]:
        """A one-letter-per-style map plus the legend, for style snapshots."""
        legend: dict[Style, str] = {}
        order = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        rows: list[str] = []
        for y in range(self.height):
            line: list[str] = []
            for x in range(self.width):
                st = self.styles[y][x]
                if st not in legend:
                    legend[st] = order[len(legend) % len(order)]
                line.append(legend[st])
            rows.append("".join(line))
        return rows, {v: k for k, v in legend.items()}

    def copy_from(self, other: "Buffer") -> None:
        self.width = other.width
        self.height = other.height
        self.chars = [row[:] for row in other.chars]
        self.styles = [row[:] for row in other.styles]


class DrawContext:
    """A view's clipped window onto the back buffer.

    Local coordinates are relative to ``origin``; nothing is written outside
    ``clip`` (an absolute rectangle) or the buffer.
    """

    def __init__(self, buffer: Buffer, origin: Point, clip: Rect):
        self.buffer = buffer
        self.origin = origin
        self.clip = clip

    def sub(self, origin: Point, clip: Rect) -> "DrawContext":
        return DrawContext(self.buffer, origin, clip.intersect(self.clip))

    def _visible(self, ax: int, ay: int) -> bool:
        return self.clip.contains_xy(ax, ay) and self.buffer.in_bounds(ax, ay)

    def put(self, x: int, y: int, ch: str, style: Style) -> None:
        ax = self.origin.x + x
        ay = self.origin.y + y
        if self._visible(ax, ay):
            self.buffer.set_cell(ax, ay, ch, style)

    def write_text(self, x: int, y: int, text: str, style: Style) -> int:
        """Write a string left-to-right from local ``(x, y)``; return columns used."""
        col = x
        for ch in text:
            if ch == "\t":
                ch = " "
            w = char_width(ch)
            if w == 0:
                continue
            ax = self.origin.x + col
            ay = self.origin.y + y
            if w == 2 and not self._visible(ax + 1, ay):
                # Wide char would fall off the clip: show a space.
                if self._visible(ax, ay):
                    self.buffer.set_cell(ax, ay, " ", style)
                col += 1
                continue
            if self._visible(ax, ay):
                self.buffer.set_cell(ax, ay, ch, style)
            col += w
        return col - x

    def fill(self, rect: Rect, ch: str, style: Style) -> None:
        for y in range(rect.y1, rect.y2):
            for x in range(rect.x1, rect.x2):
                self.put(x, y, ch, style)

    def hline(self, x: int, y: int, length: int, ch: str, style: Style) -> None:
        for i in range(length):
            self.put(x + i, y, ch, style)

    def vline(self, x: int, y: int, length: int, ch: str, style: Style) -> None:
        for i in range(length):
            self.put(x, y + i, ch, style)


class Screen:
    """Back + front buffers with a VT diff."""

    def __init__(self, width: int, height: int, depth: int = DEPTH_TRUE,
                 default_style: Style = DEFAULT_STYLE):
        self.depth = depth
        self.back = Buffer(width, height, default_style)
        self.front = Buffer(width, height, default_style)
        self.dirty = True
        self.cursor: Point | None = None

    @property
    def width(self) -> int:
        return self.back.width

    @property
    def height(self) -> int:
        return self.back.height

    def resize(self, width: int, height: int) -> None:
        self.back.resize(width, height)
        self.front.resize(width, height)
        # Force a full repaint: make front obviously different.
        self.front.clear(Style(fg=0x010101, bg=0x020202))
        self.dirty = True

    def clear(self, style: Style | None = None) -> None:
        self.back.clear(style)
        self.dirty = True

    def context(self) -> DrawContext:
        full = Rect(0, 0, self.width, self.height)
        return DrawContext(self.back, Point(0, 0), full)

    def flush(self, *, sync: bool = False) -> str:
        """Diff back against front and return the VT output; update front."""
        out: list[str] = []
        last_style: Style | None = None
        for y in range(self.height):
            bc = self.back.chars[y]
            bs = self.back.styles[y]
            if bc == self.front.chars[y] and bs == self.front.styles[y]:
                continue
            x = 0
            width = self.width
            while x < width:
                if bc[x] == self.front.chars[y][x] and bs[x] == self.front.styles[y][x]:
                    x += 1
                    continue
                out.append(f"\x1b[{y + 1};{x + 1}H")
                # Emit the changed run until cells match again.
                run_start = x
                while x < width and not (
                    bc[x] == self.front.chars[y][x] and bs[x] == self.front.styles[y][x]
                ):
                    ch = bc[x]
                    if ch == "":
                        # Right half of a wide char already emitted; skip.
                        x += 1
                        continue
                    st = bs[x]
                    if st != last_style:
                        out.append(sgr(st.fg, st.bg, st.bold, st.underline, self.depth))
                        last_style = st
                    out.append(ch if ch != "" else " ")
                    x += 1
                del run_start
        # Front now matches back.
        self.front.copy_from(self.back)
        self.dirty = False
        if not out:
            return ""
        body = "".join(out)
        if last_style is not None:
            body += "\x1b[0m"
        if sync:
            return "\x1b[?2026h" + body + "\x1b[?2026l"
        return body

    def full_render(self) -> str:
        """Render the whole back buffer from scratch (ignores front)."""
        self.front.clear(Style(fg=0x010101, bg=0x020202))
        return self.flush()
