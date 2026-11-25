# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Screen buffer, draw context, wide-char handling and the diff/flush."""

import re

from py_tvision.geometry import Point, Rect
from py_tvision.screen import Buffer, DrawContext, Screen
from py_tvision.text import char_width
from py_tvision.theme import Style

RED = Style(fg=0xFF0000, bg=0x000000)
BLUE = Style(fg=0x0000FF, bg=0x000000)


def full_ctx(buf: Buffer) -> DrawContext:
    return DrawContext(buf, Point(0, 0), Rect(0, 0, buf.width, buf.height))


def test_buffer_write_and_snapshot():
    buf = Buffer(10, 3)
    full_ctx(buf).write_text(2, 1, "hi", RED)
    rows = buf.snapshot()
    assert rows[1] == "  hi      "
    assert buf.styles[1][2] == RED


def test_clip_prevents_overflow():
    buf = Buffer(10, 2)
    ctx = DrawContext(buf, Point(0, 0), Rect(0, 0, 4, 2))
    ctx.write_text(0, 0, "abcdefgh", RED)  # only 4 cols visible
    assert buf.snapshot()[0] == "abcd      "


def test_wide_char_occupies_two_cells():
    buf = Buffer(6, 1)
    full_ctx(buf).write_text(0, 0, "中文", RED)  # 中文
    assert buf.chars[0][0] == "中"
    assert buf.chars[0][1] == ""  # right half
    assert buf.chars[0][2] == "文"
    assert buf.chars[0][3] == ""


def test_overwriting_wide_char_blanks_orphan():
    buf = Buffer(6, 1)
    ctx = full_ctx(buf)
    ctx.write_text(0, 0, "中", RED)  # wide at 0-1
    ctx.write_text(0, 0, "x", BLUE)  # narrow over the left half
    assert buf.chars[0][0] == "x"
    assert buf.chars[0][1] == " "  # orphaned right half cleared


def test_wide_char_at_last_column_becomes_space():
    buf = Buffer(3, 1)
    # Clip is full width; a wide char starting at col 2 cannot fit.
    full_ctx(buf).write_text(2, 0, "中", RED)
    assert buf.chars[0][2] == " "


def test_diff_emits_only_changed_rows():
    scr = Screen(10, 3)
    scr.full_render()  # paint baseline
    scr.back.chars[1][0] = "Z"
    out = scr.flush()
    # Only row 2 (y index 1) should be addressed.
    assert "\x1b[2;1H" in out
    assert "\x1b[1;1H" not in out
    assert "\x1b[3;1H" not in out


def test_flush_is_empty_when_nothing_changes():
    scr = Screen(8, 2)
    scr.full_render()
    assert scr.flush() == ""


# --- Round-trip: a tiny VT interpreter replays the output ------------------

_TOKEN = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|.", re.S)


def replay(output: str, width: int, height: int) -> list[str]:
    grid = [[" "] * width for _ in range(height)]
    cx = cy = 0
    for m in _TOKEN.finditer(output):
        tok = m.group(0)
        if tok.startswith("\x1b["):
            if tok.endswith("H"):
                nums = tok[2:-1].split(";")
                cy = int(nums[0]) - 1 if nums and nums[0] else 0
                cx = int(nums[1]) - 1 if len(nums) > 1 and nums[1] else 0
            # Other CSI (SGR, sync) ignored for the character round-trip.
            continue
        if tok.startswith("\x1b]"):
            continue
        if tok == "\x1b":
            continue
        if 0 <= cy < height and 0 <= cx < width:
            grid[cy][cx] = tok
            w = char_width(tok)
            if w == 2 and cx + 1 < width:
                grid[cy][cx + 1] = ""
            cx += max(1, w)
    return ["".join(c for c in row if c != "") for row in grid]


def test_round_trip_full_render():
    scr = Screen(12, 4)
    ctx = scr.context()
    ctx.write_text(0, 0, "Hello", RED)
    ctx.write_text(1, 2, "中文 world", BLUE)
    out = scr.full_render()
    assert replay(out, 12, 4) == scr.back.snapshot()


def test_round_trip_incremental():
    scr = Screen(12, 4)
    scr.context().write_text(0, 0, "aaaa", RED)
    applied = replay(scr.full_render(), 12, 4)
    # Now change a few cells and apply only the diff on top of the prior grid.
    scr.context().write_text(0, 0, "bbbb", BLUE)
    scr.back.chars  # noqa: B018 - touch for clarity
    diff = scr.flush()
    # Re-apply the diff to the previously reconstructed grid.
    merged = replay_over(applied, diff, 12, 4)
    assert merged == scr.back.snapshot()


def replay_over(grid_rows: list[str], output: str, width: int, height: int) -> list[str]:
    grid = [list(_expand(row, width)) for row in grid_rows]
    cx = cy = 0
    for m in _TOKEN.finditer(output):
        tok = m.group(0)
        if tok.startswith("\x1b["):
            if tok.endswith("H"):
                nums = tok[2:-1].split(";")
                cy = int(nums[0]) - 1 if nums and nums[0] else 0
                cx = int(nums[1]) - 1 if len(nums) > 1 and nums[1] else 0
            continue
        if tok.startswith("\x1b]") or tok == "\x1b":
            continue
        if 0 <= cy < height and 0 <= cx < width:
            grid[cy][cx] = tok
            w = char_width(tok)
            if w == 2 and cx + 1 < width:
                grid[cy][cx + 1] = ""
            cx += max(1, w)
    return ["".join(c for c in row if c != "") for row in grid]


def _expand(visual: str, width: int) -> list[str]:
    cells: list[str] = []
    for ch in visual:
        cells.append(ch)
        if char_width(ch) == 2:
            cells.append("")
    while len(cells) < width:
        cells.append(" ")
    return cells[:width]
