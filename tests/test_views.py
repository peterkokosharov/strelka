# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""View tree: focus/tab order, three-phase routing, mouse, grow/resize."""

from py_tvision.app import Program
from py_tvision.events import EventKind, Mod, broadcast_event, key_event, mouse_event
from py_tvision.geometry import Point, Rect
from py_tvision.platform.headless import HeadlessTerminal
from py_tvision.views import Grow, Group, Option, State, View


class Recorder(View):
    def __init__(self, bounds, selectable=True, handle_key=None, phase=Option.NONE):
        super().__init__(bounds)
        self.seen = []
        self.handle_key = handle_key
        if selectable:
            self.options |= Option.SELECTABLE
        self.options |= phase

    def handle_event(self, ev):
        self.seen.append((ev.kind, ev.key, ev.command))
        if self.handle_key is not None and ev.kind == EventKind.KEY and ev.key == self.handle_key:
            ev.clear()


def make_group(w=40, h=10):
    term = HeadlessTerminal(w, h)
    prog = Program(term, theme="classic")
    grp = Group(Rect(0, 1, w, h - 1))
    grp.grow_mode = Grow.HI_X | Grow.HI_Y
    prog.desktop.insert(grp)
    prog.desktop.focus_child(grp)
    return prog, grp


def test_insert_focuses_first_selectable():
    prog, grp = make_group()
    a = Recorder(Rect(0, 0, 5, 1))
    b = Recorder(Rect(0, 1, 5, 1))
    grp.insert(a)
    grp.insert(b)
    assert grp.current is a  # first selectable inserted


def test_tab_cycles_focus():
    prog, grp = make_group()
    a = Recorder(Rect(0, 0, 5, 1))
    b = Recorder(Rect(0, 1, 5, 1))
    c = Recorder(Rect(0, 2, 5, 1))
    grp.insert(a); grp.insert(b); grp.insert(c)
    grp.set_state(State.FOCUSED, True)
    order = grp._tab_order()
    assert set(order) == {a, b, c}
    first = grp.current
    grp.focus_next()
    assert grp.current is not first
    grp.focus_next(); grp.focus_next()
    assert grp.current is first  # wrapped around three


def test_focused_phase_receives_key():
    prog, grp = make_group()
    a = Recorder(Rect(0, 0, 5, 1), handle_key="X")
    grp.insert(a)
    grp.set_state(State.FOCUSED, True)
    ev = key_event("X")
    grp.handle_event(ev)
    assert ev.handled
    assert (EventKind.KEY, "X", 0) in a.seen


def test_pre_process_sees_before_focused():
    prog, grp = make_group()
    focused = Recorder(Rect(0, 0, 5, 1))
    pre = Recorder(Rect(0, 1, 5, 1), selectable=False, handle_key="H", phase=Option.PRE_PROCESS)
    grp.insert(focused)
    grp.insert(pre)
    grp.set_state(State.FOCUSED, True)
    ev = key_event("H")
    grp.handle_event(ev)
    assert ev.handled
    assert pre.seen and not focused.seen  # pre-process consumed it first


def test_post_process_sees_after_focused():
    prog, grp = make_group()
    focused = Recorder(Rect(0, 0, 5, 1))  # does not handle
    post = Recorder(Rect(0, 1, 5, 1), selectable=False, handle_key="F2", phase=Option.POST_PROCESS)
    grp.insert(focused)
    grp.insert(post)
    grp.set_state(State.FOCUSED, True)
    ev = key_event("F2")
    grp.handle_event(ev)
    assert ev.handled
    assert focused.seen and post.seen  # focused saw it first, post finished it


def test_command_broadcast_reaches_children():
    prog, grp = make_group()
    a = Recorder(Rect(0, 0, 5, 1))
    b = Recorder(Rect(0, 1, 5, 1))
    grp.insert(a); grp.insert(b)
    grp.handle_event(broadcast_event(1234))
    assert any(c == 1234 for (_k, _key, c) in a.seen)
    assert any(c == 1234 for (_k, _key, c) in b.seen)


def test_mouse_routes_to_topmost_child():
    prog, grp = make_group()
    back = Recorder(Rect(0, 0, 10, 5))
    front = Recorder(Rect(2, 1, 8, 3))  # inserted later => front of z-order
    grp.insert(back)
    grp.insert(front)
    # Point inside both; front must win.
    p = grp.abs_origin()
    ev = mouse_event(EventKind.MOUSE_DOWN, p.x + 4, p.y + 2)
    grp.handle_event(ev)
    assert front.seen and not back.seen


def test_calc_bounds_grow_modes():
    v = View(Rect(0, 0, 10, 5))
    v.grow_mode = Grow.HI_X | Grow.HI_Y
    nb = v.calc_bounds(Point(20, 10), Point(30, 14))
    assert nb == Rect(0, 0, 20, 9)  # right/bottom tracked +10/+4


def test_resize_relayouts_children():
    prog, grp = make_group(40, 12)
    child = View(Rect(0, 0, 10, 3))
    child.grow_mode = Grow.HI_X
    grp.insert(child)
    prog.resize(60, 20)
    # grp grows with the desktop; the child's right edge tracks the new width.
    assert grp.bounds.width == 60
    assert child.bounds.width > 10
