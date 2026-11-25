# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Numeric spin field: an input line restricted to a number.

A ``Spinner`` edits like an ``InputLine`` but only accepts a number within
``[minimum, maximum]``; Up/Down (and the mouse wheel) step the value by
``step``, and typing, pasting and Ctrl+V are filtered: the whole resulting
text must still be ASCII digits with an optional leading sign and - in float
mode - one decimal point, or the edit is refused. The value is the number (``value``). It takes part
in Tab focus and uses the ``input`` theme roles inherited from ``InputLine``.
"""

from __future__ import annotations

from ..events import Event, EventKind, Mod
from ..geometry import Rect
from .inputline import InputLine

_ASCII_DIGITS = frozenset("0123456789")


class Spinner(InputLine):
    def __init__(self, bounds: Rect, value: float = 0, minimum: float = 0,
                 maximum: float = 100, step: float = 1, integer: bool = True,
                 decimals: int = 2):
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.integer = integer
        self.decimals = decimals
        super().__init__(bounds, max_length=24, text="")
        self.set_value(self._clamp(value))

    # -- number <-> text ----------------------------------------------------

    def _clamp(self, val: float) -> float:
        val = max(self.minimum, min(self.maximum, val))
        return int(round(val)) if self.integer else float(val)

    def _format(self, val: float) -> str:
        if self.integer:
            return str(int(round(val)))
        return f"{val:.{self.decimals}f}"

    def _is_edit_text(self, text: str) -> bool:
        """True if ``text`` is a number, or a prefix of one, as typed.

        ASCII digits only (``str.isdigit`` and ``int`` also accept "²" or
        Arabic-Indic digits), a leading ``-`` only when negative values are
        allowed, and in float mode at most one decimal point. Partial states
        such as ``""``, ``"-"`` or ``"1."`` are valid while editing.
        """
        if text.startswith("-"):
            if self.minimum >= 0:
                return False
            text = text[1:]
        if not self.integer:
            if text.count(".") > 1:
                return False
            text = text.replace(".", "", 1)
        return all(c in _ASCII_DIGITS for c in text)

    def _parse(self, text: str) -> float | None:
        """The number in ``text``, or ``None`` if it is not (yet) a number."""
        if not self._is_edit_text(text) or not any(c in _ASCII_DIGITS for c in text):
            return None
        return int(text) if self.integer else float(text)

    @property
    def value(self) -> float:
        val = self._parse(self.data)
        if val is None:
            return self._clamp(self.minimum)
        return self._clamp(val)

    @value.setter
    def value(self, val: float) -> None:
        self.set_value(val)

    def set_value(self, val: float) -> None:
        self.data = self._format(self._clamp(val))
        self.cursor_pos = len(self.data)
        self.sel_anchor = None
        self.first = 0
        self._scroll_into_view()
        self.draw_view()

    def step_by(self, direction: int) -> None:
        self.set_value(self.value + direction * self.step)

    # -- input filtering ----------------------------------------------------

    def insert(self, text: str) -> None:
        """Insert typed, pasted or Ctrl+V text only if the whole result is
        still a valid number (or a prefix of one); otherwise change nothing."""
        before = (self.data, self.cursor_pos, self.sel_anchor, self.first)
        super().insert(text)
        if not self._is_edit_text(self.data):
            self.data, self.cursor_pos, self.sel_anchor, self.first = before
            self.draw_view()

    def _accepts(self, ch: str) -> bool:
        if ch in _ASCII_DIGITS:
            return True
        if ch == "-" and self.minimum < 0 and "-" not in self.data:
            return True
        if ch == "." and not self.integer and "." not in self.data:
            return True
        return False

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.KEY and ev.mods == Mod.NONE:
            if ev.key == "Up":
                self.step_by(1)
                ev.clear()
                return
            if ev.key == "Down":
                self.step_by(-1)
                ev.clear()
                return
            # Swallow printable keystrokes that are not part of a number.
            if ev.text and ev.text >= " " and not self._accepts(ev.text):
                ev.clear()
                return
        elif ev.kind == EventKind.MOUSE_WHEEL and self.abs_bounds().contains(ev.mouse):
            self.step_by(1 if ev.wheel > 0 else -1)
            ev.clear()
            return
        super().handle_event(ev)
