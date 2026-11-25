# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Frames, windows and dialogs.

A window is a group with a box frame and a title; the active window gets a
double-line frame, inactive windows a single line. A dialog is a window that
runs modally: Esc cancels, Enter fires the default button, and the standard
OK/Cancel commands end the modal loop with that result.
"""

from __future__ import annotations

from .events import Command, Event, EventKind, Mod
from .geometry import Point, Rect
from .screen import DrawContext
from .text import BOX_ASCII, BOX_DOUBLE, BOX_SINGLE, cut_to_width, str_width
from .views import Group, Option, State, View


class Window(Group):
    def __init__(self, bounds: Rect, title: str = "", closeable: bool = True, ascii_box: bool = False):
        super().__init__(bounds)
        self.title = title
        self.closeable = closeable
        self.ascii_box = ascii_box
        self.number = 0  # window-list number, 0 = none

    def interior(self) -> Rect:
        """The drawable area inside the frame, in local coordinates."""
        return Rect(1, 1, self.bounds.width - 1, self.bounds.height - 1)

    def _box(self) -> dict[str, str]:
        if self.ascii_box:
            return BOX_ASCII
        return BOX_DOUBLE if (self.state & State.ACTIVE) else BOX_SINGLE

    def draw_background(self, ctx: DrawContext) -> None:
        w, h = self.bounds.width, self.bounds.height
        active = bool(self.state & State.ACTIVE)
        frame_role = "window.frame.active" if active else "window.frame"
        frame = self.get_style(frame_role)
        body = self.get_style("dialog.body" if self._is_dialog() else "window")
        box = self._box()

        # Interior fill.
        ctx.fill(Rect(1, 1, w - 1, h - 1), " ", body)
        # Top and bottom borders.
        ctx.put(0, 0, box["tl"], frame)
        ctx.put(w - 1, 0, box["tr"], frame)
        ctx.put(0, h - 1, box["bl"], frame)
        ctx.put(w - 1, h - 1, box["br"], frame)
        ctx.hline(1, 0, w - 2, box["h"], frame)
        ctx.hline(1, h - 1, w - 2, box["h"], frame)
        ctx.vline(0, 1, h - 2, box["v"], frame)
        ctx.vline(w - 1, 1, h - 2, box["v"], frame)

        # Close box at the top-left.
        if self.closeable and w > 6:
            icon = self.get_style("frame.icon")
            ctx.write_text(2, 0, "[", frame)
            ctx.put(3, 0, "■" if not self.ascii_box else "x", icon)
            ctx.write_text(4, 0, "]", frame)

        # Centred title.
        if self.title:
            title_style = self.get_style("window.title")
            text = cut_to_width(self.title, w - 6)
            tw = str_width(text)
            tx = max(1, (w - tw) // 2)
            ctx.write_text(tx - 1, 0, " ", frame)
            ctx.write_text(tx, 0, text, title_style)
            ctx.write_text(tx + tw, 0, " ", frame)

    def _is_dialog(self) -> bool:
        return isinstance(self, Dialog)

    def handle_own_mouse(self, ev: Event) -> None:
        if ev.kind == EventKind.MOUSE_DOWN and self.closeable:
            o = self.abs_origin()
            if ev.mouse.y == o.y and o.x + 2 <= ev.mouse.x <= o.x + 4:
                self._on_close()
                ev.clear()

    def _on_close(self) -> None:
        if self.owner is not None:
            self.owner.remove(self)
            self.draw_view()


class Dialog(Window):
    def __init__(self, bounds: Rect, title: str = "", closeable: bool = True):
        super().__init__(bounds, title, closeable)
        self.state |= State.MODAL
        self._modal_result: int | None = None
        self.default_command = Command.OK

    def end_modal(self, command: int) -> None:
        self._modal_result = command

    def handle_event(self, ev: Event) -> None:
        # Pre-empt Esc and the default-button Enter before children.
        if ev.kind == EventKind.KEY:
            if ev.key == "Esc" and ev.mods == Mod.NONE:
                self.end_modal(Command.CANCEL)
                ev.clear()
                return
            if ev.key == "Enter" and ev.mods == Mod.NONE:
                # Let a focused button take Enter first; otherwise fire default.
                super().handle_event(ev)
                if not ev.handled:
                    from .events import command_event

                    self.handle_event_command(command_event(self.default_command))
                    ev.clear()
                return
        super().handle_event(ev)
        if not ev.handled and ev.kind in (EventKind.COMMAND, EventKind.BROADCAST):
            self.handle_own_command(ev)

    def handle_event_command(self, ev: Event) -> None:
        self.handle_event(ev)

    def handle_own_command(self, ev: Event) -> None:
        if ev.command in (Command.OK, Command.CANCEL, Command.YES, Command.NO):
            self.end_modal(ev.command)
            ev.clear()

    def _on_close(self) -> None:
        self.end_modal(Command.CANCEL)
