# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Windows KEY_EVENT_RECORD decoding (pure function, runs on every OS)."""

from py_tvision.events import Mod
from py_tvision.platform.win32 import (
    LEFT_ALT_PRESSED,
    LEFT_CTRL_PRESSED,
    RIGHT_ALT_PRESSED,
    SHIFT_PRESSED,
    decode_key_record,
)

VK_A = 0x41
VK_Q = 0x51
VK_RETURN = 0x0D
VK_LEFT = 0x25
VK_F1 = 0x70


def test_plain_letter():
    ev = decode_key_record(VK_A, "a", 0, key_down=True)
    assert ev.key == "A"
    assert ev.text == "a"
    assert ev.mods == Mod.NONE


def test_key_up_ignored():
    assert decode_key_record(VK_A, "a", 0, key_down=False) is None


def test_alt_letter_by_virtual_key():
    # Alt+Q delivers no character, but the virtual key gives us "Q".
    ev = decode_key_record(VK_Q, "", LEFT_ALT_PRESSED, key_down=True)
    assert ev.key == "Q"
    assert ev.mods & Mod.ALT


def test_altgr_yields_character_not_alt():
    # AltGr == Right-Alt + Left-Ctrl; should produce the composed char.
    state = RIGHT_ALT_PRESSED | LEFT_CTRL_PRESSED
    ev = decode_key_record(0xDB, "{", state, key_down=True)
    assert ev.text == "{"
    assert not (ev.mods & Mod.ALT)
    assert not (ev.mods & Mod.CTRL)


def test_named_key():
    assert decode_key_record(VK_RETURN, "\r", 0, key_down=True).key == "Enter"
    assert decode_key_record(VK_LEFT, "", 0, key_down=True).key == "Left"
    assert decode_key_record(VK_F1, "", 0, key_down=True).key == "F1"


def test_shift_modifier_on_named_key():
    ev = decode_key_record(VK_LEFT, "", SHIFT_PRESSED, key_down=True)
    assert ev.key == "Left" and (ev.mods & Mod.SHIFT)


def test_ctrl_letter():
    ev = decode_key_record(VK_A, "\x01", LEFT_CTRL_PRESSED, key_down=True)
    assert ev.key == "A" and (ev.mods & Mod.CTRL)
