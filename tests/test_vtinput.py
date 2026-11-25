# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""VT input decoder: keys, modifiers, mouse, paste, split reads, lone ESC."""

from py_tvision.events import EventKind, MB_LEFT, MB_RIGHT, Mod
from py_tvision.platform.vtinput import VTInputDecoder


def decode(data: bytes):
    return VTInputDecoder().feed(data)


def test_plain_text():
    evs = decode(b"abc")
    assert [e.text for e in evs] == ["a", "b", "c"]
    assert all(e.kind == EventKind.KEY for e in evs)


def test_arrows_and_home():
    assert decode(b"\x1b[A")[0].key == "Up"
    assert decode(b"\x1b[B")[0].key == "Down"
    assert decode(b"\x1b[C")[0].key == "Right"
    assert decode(b"\x1b[D")[0].key == "Left"
    assert decode(b"\x1b[H")[0].key == "Home"


def test_function_keys_ss3_and_tilde():
    assert decode(b"\x1bOP")[0].key == "F1"
    assert decode(b"\x1b[15~")[0].key == "F5"
    assert decode(b"\x1b[21~")[0].key == "F10"


def test_modified_arrow():
    ev = decode(b"\x1b[1;5A")[0]  # Ctrl+Up
    assert ev.key == "Up"
    assert ev.mods & Mod.CTRL
    ev2 = decode(b"\x1b[1;2C")[0]  # Shift+Right
    assert ev2.key == "Right" and (ev2.mods & Mod.SHIFT)


def test_alt_letter():
    ev = decode(b"\x1bq")[0]
    assert ev.key == "Q"
    assert ev.mods & Mod.ALT


def test_ctrl_letter_and_enter():
    assert decode(b"\x01")[0].key == "A" and (decode(b"\x01")[0].mods & Mod.CTRL)
    assert decode(b"\r")[0].key == "Enter"
    assert decode(b"\t")[0].key == "Tab"
    assert decode(b"\x7f")[0].key == "Backspace"


def test_delete_key():
    assert decode(b"\x1b[3~")[0].key == "Delete"


def test_sgr_mouse_down_up():
    down = decode(b"\x1b[<0;10;5M")[0]
    assert down.kind == EventKind.MOUSE_DOWN
    assert down.mouse.x == 9 and down.mouse.y == 4
    assert down.buttons & MB_LEFT
    up = decode(b"\x1b[<0;10;5m")[0]
    assert up.kind == EventKind.MOUSE_UP


def test_sgr_mouse_right_and_wheel():
    right = decode(b"\x1b[<2;3;3M")[0]
    assert right.buttons & MB_RIGHT
    wheel = decode(b"\x1b[<64;3;3M")[0]
    assert wheel.kind == EventKind.MOUSE_WHEEL
    assert wheel.wheel == 1


def test_bracketed_paste():
    evs = decode(b"\x1b[200~hello\nworld\x1b[201~")
    assert len(evs) == 1
    assert evs[0].kind == EventKind.PASTE
    assert evs[0].text == "hello\nworld"


def test_paste_split_across_reads():
    dec = VTInputDecoder()
    assert dec.feed(b"\x1b[200~par") == []
    assert dec.feed(b"tial") == []
    evs = dec.feed(b" text\x1b[201~")
    assert evs[0].text == "partial text"


def test_lone_esc_needs_flush():
    dec = VTInputDecoder()
    assert dec.feed(b"\x1b") == []  # ambiguous, waits
    evs = dec.flush()
    assert evs and evs[0].key == "Esc"


def test_csi_split_across_reads():
    dec = VTInputDecoder()
    assert dec.feed(b"\x1b[") == []
    evs = dec.feed(b"A")
    assert evs[0].key == "Up"


def test_pending_escape_flag():
    dec = VTInputDecoder()
    assert not dec.pending_escape()
    assert dec.feed(b"\x1b") == []
    assert dec.pending_escape()  # lone ESC buffered
    dec.flush()
    assert not dec.pending_escape()


def test_pending_escape_for_partial_csi():
    dec = VTInputDecoder()
    assert dec.feed(b"\x1b[") == []
    assert dec.pending_escape()  # ESC [ with nothing after


def test_stuck_csi_flushes_to_esc_without_wedging():
    # A truncated 'ESC [' that never completes must resolve to Esc on flush and
    # leave the parser clean, not wedge waiting forever.
    dec = VTInputDecoder()
    assert dec.feed(b"\x1b[") == []
    evs = dec.flush()
    assert evs and evs[0].key == "Esc"
    assert not dec.pending_escape()
    # Parser still works for the next real key.
    assert dec.feed(b"\x1b[A")[0].key == "Up"


def test_stuck_ss3_flushes_to_esc():
    dec = VTInputDecoder()
    assert dec.feed(b"\x1bO") == []
    assert dec.pending_escape()
    evs = dec.flush()
    assert evs and evs[0].key == "Esc"


def test_paste_pending_is_not_escape():
    # Mid bracketed-paste must not be mistaken for a pending escape.
    dec = VTInputDecoder()
    assert dec.feed(b"\x1b[200~partial") == []
    assert not dec.pending_escape()
    assert dec.flush() == []


def test_utf8_multibyte():
    evs = decode("中".encode("utf-8"))
    assert evs[0].text == "中"
