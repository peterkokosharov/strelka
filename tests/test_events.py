# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Event construction, key specs and the thread-safe post queue."""

import threading

from py_tvision.events import (
    Command,
    EventKind,
    Mod,
    PostQueue,
    command_event,
    key_event,
    key_spec,
)


def test_key_event_predicates():
    ev = key_event("Q", Mod.ALT)
    assert ev.is_key("Q", Mod.ALT)
    assert not ev.is_key("Q")
    assert ev.kind == EventKind.KEY


def test_clear_marks_handled():
    ev = key_event("A")
    assert not ev.handled
    ev.clear()
    assert ev.handled


def test_command_event_predicate():
    ev = command_event(Command.OK)
    assert ev.is_command(Command.OK)
    assert not ev.is_command(Command.CANCEL)


def test_key_spec():
    assert key_spec("Alt+Q") == ("Q", Mod.ALT)
    assert key_spec("Ctrl+Enter") == ("Enter", Mod.CTRL)
    assert key_spec("F1") == ("F1", Mod.NONE)
    name, mods = key_spec("Ctrl+Shift+A")
    assert name == "A" and (mods & Mod.CTRL) and (mods & Mod.SHIFT)


def test_post_queue_fifo_and_wake():
    woken = []
    q = PostQueue(wake=lambda: woken.append(1))
    q.post(key_event("A"))
    q.post(key_event("B"))
    items = q.drain()
    assert [e.key for e in items] == ["A", "B"]
    assert len(woken) == 2
    assert q.empty()


def test_post_queue_threadsafe():
    q = PostQueue()
    total = 200

    def worker(start):
        for i in range(start, start + 100):
            q.post(key_event(str(i)))

    t1 = threading.Thread(target=worker, args=(0,))
    t2 = threading.Thread(target=worker, args=(100,))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert len(q.drain()) == total
