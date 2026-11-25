# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Character width and text helpers.

Column width follows the common terminal rules: East-Asian Wide/Fullwidth
characters take two columns, combining marks and zero-width formatting take
none, everything else takes one. This mirrors the ``cpWidth`` table in
Layka's ``core.h`` (Markus Kuhn style) closely enough to lay the same text
out identically; the tests cross-check the interesting ranges.
"""

from __future__ import annotations

import unicodedata

# Box-drawing character sets. The renderer picks the ASCII set when the
# terminal is not known to be UTF-8 capable.
BOX_SINGLE = {
    "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
    "h": "─", "v": "│",
    "lt": "├", "rt": "┤", "tt": "┬", "bt": "┴", "x": "┼",
}
BOX_DOUBLE = {
    "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
    "h": "═", "v": "║",
    "lt": "╠", "rt": "╣", "tt": "╦", "bt": "╩", "x": "╬",
}
BOX_ASCII = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+",
    "h": "-", "v": "|",
    "lt": "+", "rt": "+", "tt": "+", "bt": "+", "x": "+",
}

SHADE_LIGHT = "░"  # ░
SHADE_MEDIUM = "▒"  # ▒
ARROW_UP = "▲"  # ▲
ARROW_DOWN = "▼"  # ▼
ARROW_LEFT = "◄"  # ◄
ARROW_RIGHT = "►"  # ►


# Placeholder shown in place of a stripped control character. A middle dot is
# visible (unlike a space, which would hide that something was removed), width
# 1, and present in every bundled theme font.
SAFE_PLACEHOLDER = "·"  # ·


def is_unsafe_control(ch: str) -> bool:
    """True if ``ch`` is a control character that must not reach the terminal.

    Covers the C0 range U+0000-U+001F (which includes ESC), DEL U+007F, and
    the C1 range U+0080-U+009F. These can move the cursor, clear the screen or
    recolour the terminal if emitted raw, so untrusted text must never carry
    them through to the VT flush. Lone surrogates U+D800-U+DFFF (possible in
    Windows file names, PEP 529) are included too: they cannot be encoded to
    UTF-8/UTF-16 and would break the whole frame write. The test is a cheap
    ``ord`` range check.
    """
    if len(ch) != 1:
        return False
    cp = ord(ch)
    return (cp <= 0x1F or cp == 0x7F or 0x80 <= cp <= 0x9F
            or 0xD800 <= cp <= 0xDFFF)


def safe_glyph(ch: str) -> str:
    """Return ``ch`` unchanged, or the placeholder if it is an unsafe control
    character or a lone surrogate."""
    return SAFE_PLACEHOLDER if is_unsafe_control(ch) else ch


def char_width(ch: str) -> int:
    """Return the number of terminal columns a single character occupies."""
    if not ch:
        return 0
    cp = ord(ch)
    if cp == 0:
        return 0
    if cp < 32 or cp == 0x7F:
        # Control characters are not printed as-is; treat as width 1 (a caller
        # that wants them hidden should strip them first).
        return 1
    category = unicodedata.category(ch)
    if category in ("Mn", "Me", "Cf"):
        return 0
    if ch in ("​", "‌", "‍", "﻿"):  # zero-width spaces/joiner/BOM
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def str_width(s: str) -> int:
    """Total column width of a string."""
    return sum(char_width(ch) for ch in s)


def cut_to_width(s: str, width: int) -> str:
    """Truncate ``s`` so it fits in ``width`` columns.

    If a wide character would be split by the limit it is dropped (not
    half-shown); the result's column width is therefore ``<= width``.
    """
    if width <= 0:
        return ""
    out: list[str] = []
    used = 0
    for ch in s:
        w = char_width(ch)
        if used + w > width:
            break
        out.append(ch)
        used += w
    return "".join(out)


def pad_to_width(s: str, width: int, fill: str = " ", align: str = "left") -> str:
    """Cut or pad ``s`` to exactly ``width`` columns."""
    s = cut_to_width(s, width)
    gap = width - str_width(s)
    if gap <= 0:
        return s
    pad = fill * gap
    if align == "right":
        return pad + s
    if align == "center":
        left = gap // 2
        return fill * left + s + fill * (gap - left)
    return s + pad


def parse_hotkey(label: str) -> tuple[str, str | None, int]:
    """Parse a ``~X~`` hotkey marker in a label.

    Returns ``(display_text, hotkey_char, index)`` where ``display_text`` has
    the tildes removed, ``hotkey_char`` is the highlighted character in upper
    case (or ``None`` if there is no marker), and ``index`` is the column of
    that character within ``display_text`` (``-1`` when absent).
    """
    out: list[str] = []
    hotkey: str | None = None
    index = -1
    i = 0
    n = len(label)
    col = 0
    while i < n:
        ch = label[i]
        if ch == "~" and i + 1 < n:
            # ~X~ : take the next character (until the closing tilde) as hot.
            j = i + 1
            segment: list[str] = []
            while j < n and label[j] != "~":
                segment.append(label[j])
                j += 1
            if segment and hotkey is None:
                hotkey = segment[0].upper()
                index = col
            for c in segment:
                out.append(c)
                col += char_width(c)
            i = j + 1 if j < n else j
        else:
            out.append(ch)
            col += char_width(ch)
            i += 1
    return "".join(out), hotkey, index
