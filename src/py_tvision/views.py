# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Views and groups: the tree, drawing, focus and event routing.

Every visible thing is a :class:`View` with bounds relative to its owner. A
:class:`Group` owns children in z-order, draws them back to front with
clipping, and routes events. Key events take three phases (pre-process,
focused chain, post-process) so a button reacts to its Alt-hotkey and a
status line to an F-key even when neither is focused; mouse events go to the
top-most view under the pointer; commands broadcast to every child.
"""

from __future__ import annotations

from enum import IntFlag

from .events import Event, EventKind, Mod
from .geometry import Point, Rect
from .screen import DrawContext
from .theme import Style, Theme


class State(IntFlag):
    NONE = 0
    VISIBLE = 1
    FOCUSED = 2
    SELECTED = 4
    ACTIVE = 8
    DISABLED = 16
    MODAL = 32
    CURSOR_VIS = 64


class Option(IntFlag):
    NONE = 0
    SELECTABLE = 1
    PRE_PROCESS = 2
    POST_PROCESS = 4
    FIRST_CLICK = 8
    CENTERED = 16


class Grow(IntFlag):
    NONE = 0
    LO_X = 1  # left edge tracks the right side
    LO_Y = 2
    HI_X = 4  # right edge tracks the right side
    HI_Y = 8
    REL = 16  # keep proportional (used for centred dialogs)


class View:
    def __init__(self, bounds: Rect):
        self.owner: "Group | None" = None
        self.bounds = bounds
        self.state: State = State.VISIBLE
        self.options: Option = Option.NONE
        self.grow_mode: Grow = Grow.NONE
        self.cursor: Point | None = None  # local cursor position, if any
        self._role_overrides: dict[str, Style] = {}

    # -- tree / geometry ----------------------------------------------------

    @property
    def size(self) -> Point:
        return Point(self.bounds.width, self.bounds.height)

    def abs_origin(self) -> Point:
        x, y = self.bounds.x1, self.bounds.y1
        owner = self.owner
        while owner is not None:
            x += owner.bounds.x1
            y += owner.bounds.y1
            owner = owner.owner
        return Point(x, y)

    def abs_bounds(self) -> Rect:
        o = self.abs_origin()
        return Rect(o.x, o.y, o.x + self.bounds.width, o.y + self.bounds.height)

    def program(self) -> "object | None":
        node: View | None = self
        while node is not None and node.owner is not None:
            node = node.owner
        return node

    # -- state --------------------------------------------------------------

    def set_state(self, flag: State, on: bool) -> None:
        if on:
            self.state |= flag
        else:
            self.state &= ~flag
        self.draw_view()

    def get_state(self, flag: State) -> bool:
        return bool(self.state & flag)

    def is_selectable(self) -> bool:
        return (
            bool(self.options & Option.SELECTABLE)
            and bool(self.state & State.VISIBLE)
            and not (self.state & State.DISABLED)
        )

    # -- theme / style ------------------------------------------------------

    def theme(self) -> Theme | None:
        prog = self.program()
        return getattr(prog, "the_theme", None)

    def set_role(self, role: str, style: Style) -> None:
        self._role_overrides[role] = style

    def get_style(self, role: str) -> Style:
        if role in self._role_overrides:
            return self._role_overrides[role]
        th = self.theme()
        if th is not None:
            return th.style(role)
        return Style()

    # -- drawing ------------------------------------------------------------

    def draw(self, ctx: DrawContext) -> None:
        """Draw this view into its clipped context. Override in subclasses."""

    def draw_view(self) -> None:
        """Mark the screen dirty so the loop repaints this turn."""
        prog = self.program()
        screen = getattr(prog, "screen", None)
        if screen is not None:
            screen.dirty = True

    def put_event(self, ev: Event) -> None:
        """Hand an event to the program's queue (processed next loop turn)."""
        prog = self.program()
        put = getattr(prog, "put_event", None)
        if put is not None:
            put(ev)

    def emit_command(self, command: int, info: object | None = None) -> None:
        from .events import command_event

        self.put_event(command_event(command, info if info is not None else self))

    # -- focus --------------------------------------------------------------

    def focus(self) -> None:
        if self.owner is not None:
            self.owner.focus_child(self)
            self.owner.focus()

    # -- grow / resize ------------------------------------------------------

    def calc_bounds(self, old_owner: Point, new_owner: Point) -> Rect:
        """Compute new bounds when the owner grows from ``old`` to ``new`` size."""
        dx = new_owner.x - old_owner.x
        dy = new_owner.y - old_owner.y
        g = self.grow_mode
        x1, y1, x2, y2 = self.bounds.x1, self.bounds.y1, self.bounds.x2, self.bounds.y2
        if g & Grow.REL:
            if old_owner.x:
                x1 = round(x1 * new_owner.x / old_owner.x)
                x2 = round(x2 * new_owner.x / old_owner.x)
            if old_owner.y:
                y1 = round(y1 * new_owner.y / old_owner.y)
                y2 = round(y2 * new_owner.y / old_owner.y)
            return Rect(x1, y1, x2, y2)
        if g & Grow.LO_X:
            x1 += dx
        if g & Grow.HI_X:
            x2 += dx
        if g & Grow.LO_Y:
            y1 += dy
        if g & Grow.HI_Y:
            y2 += dy
        return Rect(x1, y1, x2, y2)

    def change_bounds(self, new_bounds: Rect) -> None:
        self.bounds = new_bounds
        self.draw_view()

    # -- events -------------------------------------------------------------

    def handle_event(self, ev: Event) -> None:
        """Default view handles nothing."""


class Group(View):
    def __init__(self, bounds: Rect):
        super().__init__(bounds)
        self.children: list[View] = []
        self.current: View | None = None

    # -- insertion ----------------------------------------------------------

    def insert(self, view: View) -> None:
        view.owner = self
        self.children.insert(0, view)  # front of z-order
        if view.is_selectable() and self.current is None:
            self.focus_child(view)

    def remove(self, view: View) -> None:
        if view in self.children:
            self.children.remove(view)
            view.owner = None
            if self.current is view:
                self.current = self._first_selectable()
                if self.current is not None and self.get_state(State.FOCUSED):
                    self.current.set_state(State.FOCUSED, True)

    def _first_selectable(self) -> View | None:
        for c in reversed(self.children):  # draw/tab order
            if c.is_selectable():
                return c
        return None

    # -- focus --------------------------------------------------------------

    def focus_child(self, child: View) -> None:
        if child is self.current:
            if self.get_state(State.FOCUSED):
                child.set_state(State.FOCUSED, True)
            return
        if self.current is not None and self.get_state(State.FOCUSED):
            self.current.set_state(State.FOCUSED, False)
        self.current = child
        if child is not None and self.get_state(State.FOCUSED):
            child.set_state(State.FOCUSED, True)

    def set_state(self, flag: State, on: bool) -> None:
        super().set_state(flag, on)
        if flag & State.FOCUSED and self.current is not None:
            self.current.set_state(State.FOCUSED, on)

    def _tab_order(self) -> list[View]:
        # Visual/tab order is the reverse of the z-order list.
        return [c for c in reversed(self.children) if c.is_selectable()]

    def focus_next(self, backward: bool = False) -> None:
        order = self._tab_order()
        if not order:
            return
        if self.current in order:
            i = order.index(self.current)
            i = (i - 1 if backward else i + 1) % len(order)
        else:
            i = 0
        self.focus_child(order[i])

    # -- drawing ------------------------------------------------------------

    def draw_background(self, ctx: DrawContext) -> None:
        """Groups with their own backdrop override this."""

    def draw(self, ctx: DrawContext) -> None:
        self.draw_background(ctx)
        for child in reversed(self.children):  # back to front
            if not (child.state & State.VISIBLE):
                continue
            corigin = Point(ctx.origin.x + child.bounds.x1, ctx.origin.y + child.bounds.y1)
            cbounds = Rect(corigin.x, corigin.y,
                           corigin.x + child.bounds.width, corigin.y + child.bounds.height)
            cclip = cbounds.intersect(ctx.clip)
            if cclip.is_empty():
                continue
            child.draw(DrawContext(ctx.buffer, corigin, cclip))

    # -- mouse hit test -----------------------------------------------------

    def _child_at(self, p: Point) -> View | None:
        for child in self.children:  # front to back
            if not (child.state & State.VISIBLE):
                continue
            if child.abs_bounds().contains(p):
                return child
        return None

    # -- event routing ------------------------------------------------------

    def handle_event(self, ev: Event) -> None:
        if ev.kind in (EventKind.KEY, EventKind.PASTE):
            self._route_key(ev)
        elif ev.kind in (EventKind.COMMAND, EventKind.BROADCAST):
            self._route_command(ev)
        elif ev.kind in (EventKind.MOUSE_DOWN, EventKind.MOUSE_UP,
                         EventKind.MOUSE_MOVE, EventKind.MOUSE_WHEEL):
            self._route_mouse(ev)

    def _route_key(self, ev: Event) -> None:
        for c in list(self.children):
            if c.options & Option.PRE_PROCESS:
                c.handle_event(ev)
                if ev.handled:
                    return
        if self.current is not None:
            self.current.handle_event(ev)
            if ev.handled:
                return
        for c in list(self.children):
            if c.options & Option.POST_PROCESS:
                c.handle_event(ev)
                if ev.handled:
                    return
        # Group-level Tab focus movement.
        if ev.kind == EventKind.KEY and ev.key == "Tab":
            self.focus_next(backward=bool(ev.mods & Mod.SHIFT))
            ev.clear()

    def _route_command(self, ev: Event) -> None:
        for c in list(self.children):
            c.handle_event(ev)
            if ev.handled:
                return
        self.handle_own_command(ev)

    def _route_mouse(self, ev: Event) -> None:
        target = self._child_at(ev.mouse)
        if target is not None:
            if (ev.kind == EventKind.MOUSE_DOWN and target.is_selectable()
                    and target is not self.current):
                self.focus_child(target)
            target.handle_event(ev)
            if ev.handled:
                return
        self.handle_own_mouse(ev)

    def handle_own_command(self, ev: Event) -> None:
        """Override to react to a command no child consumed."""

    def handle_own_mouse(self, ev: Event) -> None:
        """Override to react to a mouse event no child consumed."""

    # -- resize -------------------------------------------------------------

    def change_bounds(self, new_bounds: Rect) -> None:
        old = Point(self.bounds.width, self.bounds.height)
        super().change_bounds(new_bounds)
        new = Point(new_bounds.width, new_bounds.height)
        if old != new:
            for child in self.children:
                child.change_bounds(child.calc_bounds(old, new))
