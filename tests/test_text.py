# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Width and text-helper tests, including wide and combining characters."""

from py_tvision.text import (
    char_width,
    cut_to_width,
    pad_to_width,
    parse_hotkey,
    str_width,
)


def test_ascii_width():
    assert char_width("A") == 1
    assert str_width("hello") == 5


def test_wide_cjk_width():
    assert char_width("中") == 2  # 中
    assert char_width("Ａ") == 2  # fullwidth A
    assert str_width("中文") == 4  # 中文


def test_combining_is_zero_width():
    assert char_width("́") == 0  # combining acute accent
    # "e" + combining accent = one column
    assert str_width("é") == 1


def test_zero_width_and_control():
    assert char_width("​") == 0  # zero-width space
    assert char_width("‍") == 0  # ZWJ
    assert char_width("\x00") == 0


def test_cut_to_width_ascii():
    assert cut_to_width("hello world", 5) == "hello"
    assert cut_to_width("hi", 10) == "hi"
    assert cut_to_width("x", 0) == ""


def test_cut_does_not_split_wide_char():
    # Two wide chars = 4 columns; cutting to 3 keeps only the first (2 cols).
    s = "中文"
    out = cut_to_width(s, 3)
    assert out == "中"
    assert str_width(out) <= 3


def test_pad_alignments():
    assert pad_to_width("ab", 5) == "ab   "
    assert pad_to_width("ab", 5, align="right") == "   ab"
    assert pad_to_width("ab", 6, align="center") == "  ab  "
    assert str_width(pad_to_width("中", 5)) == 5


def test_parse_hotkey():
    disp, hot, idx = parse_hotkey("~F~ile")
    assert disp == "File"
    assert hot == "F"
    assert idx == 0


def test_parse_hotkey_middle():
    disp, hot, idx = parse_hotkey("E~x~it")
    assert disp == "Exit"
    assert hot == "X"
    assert idx == 1


def test_parse_hotkey_none():
    disp, hot, idx = parse_hotkey("Plain")
    assert disp == "Plain"
    assert hot is None
    assert idx == -1
