# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Colour mapping and depth detection tests."""

from py_tvision.color import (
    DEPTH_16,
    DEPTH_256,
    DEPTH_MONO,
    DEPTH_TRUE,
    detect_depth,
    rgb,
    rgb_to_16,
    rgb_to_256,
    sgr,
    split,
)


def test_rgb_split_roundtrip():
    c = rgb(18, 52, 86)
    assert split(c) == (18, 52, 86)


def test_rgb_to_16_primaries():
    assert rgb_to_16(0x000000) == 0
    assert rgb_to_16(0xFFFFFF) == 15
    assert rgb_to_16(0xFF0000) == 9  # bright red
    assert rgb_to_16(0x00FF00) == 10


def test_rgb_to_256_extremes():
    assert rgb_to_256(0x000000) == 16
    assert rgb_to_256(0xFFFFFF) == 231
    # A mid grey should land on the grey ramp (232..255).
    assert 232 <= rgb_to_256(0x808080) <= 255


def test_detect_depth_overrides():
    # NO_COLOR (any value, convention from no-color.org) suppresses colour.
    assert detect_depth({"NO_COLOR": "1"}) == DEPTH_MONO
    # An empty NO_COLOR does not count (no-color.org: "present and not empty").
    assert detect_depth({"NO_COLOR": ""}) != DEPTH_MONO
    assert detect_depth({"STRELKA_COLORS": "24bit"}) == DEPTH_TRUE
    assert detect_depth({"STRELKA_COLORS": "256"}) == DEPTH_256
    assert detect_depth({"STRELKA_COLORS": "16"}) == DEPTH_16


def test_detect_depth_four_levels_and_default():
    # Representative env dicts -> true / 256 / 16 / mono.
    assert detect_depth({"COLORTERM": "truecolor"}) == DEPTH_TRUE
    assert detect_depth({"TERM": "screen-256color"}) == DEPTH_256
    assert detect_depth({"TERM": "dumb"}) == DEPTH_16
    assert detect_depth({"NO_COLOR": "yes"}) == DEPTH_MONO
    # Nothing detectable at all -> truecolor default.
    assert detect_depth({}) == DEPTH_TRUE


def test_sgr_downgrade_by_depth():
    # The same truecolor style emits 24-bit at depth true, a 16-colour SGR at
    # depth 16, and no colour at all at mono.
    true = sgr(0xFF0000, 0x000000, False, False, DEPTH_TRUE)
    assert "38;2;255;0;0" in true
    s16 = sgr(0xFF0000, 0x000000, False, False, DEPTH_16)
    assert "38;2;" not in s16 and "38;5;" not in s16  # no truecolor/256 escape
    assert "91" in s16.strip("\x1b[m").split(";")  # bright red (90+9)
    mono = sgr(0xFF0000, 0x00FF00, True, True, DEPTH_MONO)
    # Attributes survive, colour does not.
    body = mono.strip("\x1b[m").split(";")
    assert "1" in body and "4" in body
    assert not any(p.startswith(("38", "48")) for p in body)


def test_detect_depth_from_term():
    assert detect_depth({"COLORTERM": "truecolor"}) == DEPTH_TRUE
    assert detect_depth({"WT_SESSION": "x"}) == DEPTH_TRUE
    assert detect_depth({"TERM": "xterm-256color"}) == DEPTH_256
    assert detect_depth({"TERM": "dumb"}) == DEPTH_16


def test_sgr_truecolor():
    s = sgr(0x112233, 0x445566, False, False, DEPTH_TRUE)
    assert "38;2;17;34;51" in s
    assert "48;2;68;85;102" in s
    assert s.startswith("\x1b[") and s.endswith("m")


def test_sgr_256_and_16():
    s256 = sgr(0xFFFFFF, 0x000000, False, False, DEPTH_256)
    assert "38;5;" in s256
    s16 = sgr(0xFFFFFF, 0x000000, True, False, DEPTH_16)
    assert "1" in s16.strip("\x1b[m").split(";")  # bold
