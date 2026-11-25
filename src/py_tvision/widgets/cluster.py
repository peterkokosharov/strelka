# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Checkbox and radio-button clusters.

A cluster is one selectable view holding a column of labelled items, each
with an optional ``~X~`` hotkey. ``CheckBoxes`` is multi-select (its value is
the set of checked indices, also available as a bitmask); ``RadioButtons`` is
single-select (its value is the selected index). Up/Down move the focus,
Space toggles (checkboxes) or confirms (radios), Alt-hotkey and a mouse click
act on a specific item. The cluster takes part in Tab focus and works inside a
dialog; colours come from the ``label`` and ``list.focused`` theme roles so it
renders in all three themes without new role entries.
"""

from __future__ import annotations

from ..events import Event, EventKind, Mod
from ..geometry import Rect
from ..screen import DrawContext
from ..text import cut_to_width, parse_hotkey, str_width
from ..views import Option, State, View

MARK_WIDTH = 4  # columns used by "[X] " / "(o) " before the item label


class _Cluster(View):
    """Shared behaviour for checkbox and radio clusters."""

    def __init__(self, bounds: Rect, labels: list[str]):
        super().__init__(bounds)
        # Each item: (display_text, hotkey_char_or_None, hotkey_column).
        self.items = [parse_hotkey(text) for text in labels]
        self.focused_index = 0
        self.options |= Option.SELECTABLE | Option.PRE_PROCESS | Option.FIRST_CLICK

    # -- to be provided by subclasses --------------------------------------

    def _mark(self, index: int) -> str:
        raise NotImplementedError

    def _space(self, index: int) -> None:
        """React to Space on the focused item."""

    def _activate(self, index: int) -> None:
        """React to an Alt-hotkey or a mouse click on ``index``."""

    # -- navigation ---------------------------------------------------------

    def _move(self, new_index: int) -> None:
        if not self.items:
            return
        self.focused_index = max(0, min(len(self.items) - 1, new_index))
        self.draw_view()

    # -- drawing ------------------------------------------------------------

    def draw(self, ctx: DrawContext) -> None:
        focused_widget = bool(self.state & State.FOCUSED)
        base = self.get_style("label")
        hot = self.get_style("label.hotkey")
        sel = self.get_style("list.focused")
        w, h = self.bounds.width, self.bounds.height
        ctx.fill(Rect(0, 0, w, h), " ", base)
        for index, (disp, hotkey, hidx) in enumerate(self.items):
            if index >= h:
                break
            on_focus = focused_widget and index == self.focused_index
            style = sel if on_focus else base
            if on_focus:
                ctx.fill(Rect(0, index, w, index + 1), " ", style)
            line = self._mark(index) + disp
            ctx.write_text(0, index, cut_to_width(line, w), style)
            if hotkey is not None and not on_focus and 0 <= hidx < len(disp):
                col = MARK_WIDTH + hidx
                if col < w:
                    ctx.put(col, index, disp[hidx], hot)

    # -- events -------------------------------------------------------------

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.KEY:
            # Alt-hotkey works regardless of focus (pre-process phase).
            if ev.mods & Mod.ALT:
                for i, (_disp, hotkey, _hidx) in enumerate(self.items):
                    if hotkey is not None and ev.key == hotkey:
                        self.focus()
                        self._move(i)
                        self._activate(i)
                        ev.clear()
                        return
            if bool(self.state & State.FOCUSED) and ev.mods == Mod.NONE:
                if ev.key == "Up":
                    self._move(self.focused_index - 1)
                    ev.clear()
                elif ev.key == "Down":
                    self._move(self.focused_index + 1)
                    ev.clear()
                elif ev.key == "Home":
                    self._move(0)
                    ev.clear()
                elif ev.key == "End":
                    self._move(len(self.items) - 1)
                    ev.clear()
                elif ev.key == " ":
                    self._space(self.focused_index)
                    ev.clear()
        elif ev.kind == EventKind.MOUSE_DOWN and self.abs_bounds().contains(ev.mouse):
            row = ev.mouse.y - self.abs_origin().y
            if 0 <= row < len(self.items):
                self._move(row)
                self._activate(row)
            ev.clear()


class CheckBoxes(_Cluster):
    """A multi-select cluster; the value is the set of checked indices."""

    def __init__(self, bounds: Rect, labels: list[str],
                 checked: set[int] | None = None):
        super().__init__(bounds, labels)
        self.checked: set[int] = set(checked) if checked else set()

    def _mark(self, index: int) -> str:
        return "[X] " if index in self.checked else "[ ] "

    def _toggle(self, index: int) -> None:
        if index in self.checked:
            self.checked.discard(index)
        else:
            self.checked.add(index)
        self.draw_view()

    def _space(self, index: int) -> None:
        self._toggle(index)

    def _activate(self, index: int) -> None:
        self._toggle(index)

    def is_checked(self, index: int) -> bool:
        return index in self.checked

    @property
    def value(self) -> set[int]:
        return set(self.checked)

    @value.setter
    def value(self, indices) -> None:
        self.checked = set(indices)
        self.draw_view()

    @property
    def mask(self) -> int:
        """The checked set as a bitmask (bit ``i`` set when item ``i`` is on)."""
        bits = 0
        for i in self.checked:
            bits |= 1 << i
        return bits

    @mask.setter
    def mask(self, bits: int) -> None:
        self.checked = {i for i in range(len(self.items)) if bits & (1 << i)}
        self.draw_view()


class RadioButtons(_Cluster):
    """A single-select cluster; the value is the selected index."""

    def __init__(self, bounds: Rect, labels: list[str], selected: int = 0):
        super().__init__(bounds, labels)
        self.focused_index = max(0, min(selected, len(self.items) - 1)) if self.items else 0

    def _mark(self, index: int) -> str:
        return "(o) " if index == self.focused_index else "( ) "

    def _move(self, new_index: int) -> None:
        # Moving the cursor also moves the selection (value tracks focus).
        super()._move(new_index)

    def _space(self, index: int) -> None:
        # The focused item is already the selection; redraw for feedback.
        self.focused_index = index
        self.draw_view()

    def _activate(self, index: int) -> None:
        self.focused_index = index
        self.draw_view()

    @property
    def value(self) -> int:
        return self.focused_index

    @value.setter
    def value(self, index: int) -> None:
        self._move(index)

    def selected_label(self) -> str:
        if 0 <= self.focused_index < len(self.items):
            return self.items[self.focused_index][0]
        return ""
