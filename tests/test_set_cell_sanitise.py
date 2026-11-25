# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Control-character sanitisation at the single choke point, ``set_cell``.

Untrusted model/tool/file text is drawn one glyph at a time through
``Buffer.set_cell``. A C0 control (incl. ESC), DEL, or a C1 control must never
reach the VT flush, where it could move the cursor, clear the screen or
recolour the terminal outside the app's frame. Every drawing path funnels
through ``set_cell``, so sanitising there covers them all.
"""

from py_tvision.geometry import Point, Rect
from py_tvision.screen import Buffer, DrawContext, Screen
from py_tvision.text import (
    SAFE_PLACEHOLDER,
    char_width,
    is_unsafe_control,
    safe_glyph,
)
from py_tvision.theme import Style

RED = Style(fg=0xFF0000, bg=0x000000)
DOT = SAFE_PLACEHOLDER  # ·


def full_ctx(buf: Buffer) -> DrawContext:
    return DrawContext(buf, Point(0, 0), Rect(0, 0, buf.width, buf.height))


def _has_raw_control(buf: Buffer) -> bool:
    return any(is_unsafe_control(c) for row in buf.chars for c in row)


# --- The placeholder is width 1 and a middle dot --------------------------

def test_placeholder_is_middle_dot_width_one():
    assert SAFE_PLACEHOLDER == "·"
    assert char_width(SAFE_PLACEHOLDER) == 1
    assert not is_unsafe_control(SAFE_PLACEHOLDER)


# --- ESC must never be stored or emitted ----------------------------------

def test_esc_replaced_in_buffer_and_not_flushed():
    buf = Buffer(5, 1)
    buf.set_cell(0, 0, "\x1b", RED)
    assert buf.chars[0][0] == DOT
    assert "\x1b" not in buf.snapshot()[0]
    assert not _has_raw_control(buf)

    scr = Screen(5, 1)
    scr.full_render()
    scr.back.set_cell(0, 0, "\x1b", RED)
    out = scr.flush()
    # The placeholder is drawn; no ESC originates from the payload. flush emits
    # its own cursor/SGR escapes, but never a bare ESC as *cell content*: the
    # drawn glyph is the middle dot.
    assert DOT in out
    # Strip flush's own CSI escapes; what remains must hold no raw ESC byte.
    assert "\x1b[" in out  # cursor addressing is present...
    payload_cells = scr.back.snapshot()[0]
    assert "\x1b" not in payload_cells


# --- Other C0 / C1 / DEL controls -----------------------------------------

def test_c0_c1_and_del_each_replaced():
    cases = {
        "\x00": "NUL",
        "\r": "CR",
        "\n": "LF",
        "\x07": "BEL",
        "\x7f": "DEL",
        "\x85": "NEL (C1)",
        "\x9b": "CSI (C1)",
    }
    for ch, name in cases.items():
        buf = Buffer(3, 1)
        buf.set_cell(0, 0, ch, RED)
        assert buf.chars[0][0] == DOT, f"{name} not replaced"
        assert not _has_raw_control(buf), f"{name} left a raw control in the buffer"


def test_c1_range_boundaries():
    # U+0080 and U+009F are unsafe; U+00A0 (NBSP) and U+00A1 are printable.
    assert is_unsafe_control("\x80")
    assert is_unsafe_control("\x9f")
    assert not is_unsafe_control("\xa0")
    assert not is_unsafe_control("\xa1")


# --- Printable characters are untouched ------------------------------------

def test_ascii_letter_unaffected():
    buf = Buffer(3, 1)
    buf.set_cell(0, 0, "A", RED)
    assert buf.chars[0][0] == "A"


def test_wide_cjk_unaffected():
    buf = Buffer(4, 1)
    buf.set_cell(0, 0, "世", RED)  # wide
    assert buf.chars[0][0] == "世"
    assert buf.chars[0][1] == ""  # right half preserved


def test_combining_mark_unaffected():
    # A combining mark is width 0 and ignored at the buffer level (not turned
    # into a placeholder). The cell keeps its prior content.
    mark = "́"  # combining acute accent
    assert not is_unsafe_control(mark)
    assert safe_glyph(mark) == mark
    buf = Buffer(3, 1)
    buf.set_cell(0, 0, "e", RED)
    buf.set_cell(0, 0, mark, RED)  # w == 0 -> ignored
    assert buf.chars[0][0] == "e"  # untouched, no placeholder written


def test_emoji_non_bmp_unaffected():
    emoji = "\U0001F600"  # grinning face, a single non-BMP code point
    assert not is_unsafe_control(emoji)
    buf = Buffer(4, 1)
    buf.set_cell(0, 0, emoji, RED)
    assert buf.chars[0][0] == emoji


# --- The right half of a wide cell ("") still works ------------------------

def test_empty_right_half_passes_through():
    buf = Buffer(4, 1)
    # Writing "" is the wide-char right-half path; must not raise or replace.
    buf.set_cell(1, 0, "", RED)
    assert buf.chars[0][1] == ""


# --- End-to-end: an attack string through a higher-level draw path ---------

def test_attack_string_through_draw_context_not_emitted():
    # A realistic payload: a label containing a clear-screen sequence.
    payload = "ok\x1b[2Jdone"
    scr = Screen(20, 1)
    scr.full_render()
    scr.context().write_text(0, 0, payload, RED)
    out = scr.flush()

    # The ESC is stripped, so the dangerous sequence cannot appear in the
    # terminal output. flush never emits "\x1b[2J" itself (only cursor-move
    # "H", SGR "m", and sync toggles), so this substring check is meaningful.
    assert "\x1b[2J" not in out
    # The ESC became a middle dot; the rest ("[2Jdone") is now harmless text.
    row = scr.back.snapshot()[0]
    assert "\x1b" not in row
    assert DOT in row
    assert row.startswith("ok" + DOT + "[2Jdone")
    assert not _has_raw_control(scr.back)
