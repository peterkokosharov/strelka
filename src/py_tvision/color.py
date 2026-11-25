# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Colour representation and RGB -> xterm-256 / 16 downgrade.

Colours are plain 24-bit integers (``0xRRGGBB``). The renderer asks for an
SGR string at the terminal's actual depth; the mapping down to 256 or 16
colours is our own (nearest cube/grey entry, then nearest of the 16 base
colours by weighted distance). magiblot's HCL approach could replace this
later if the simple mapping ever looks wrong.
"""

from __future__ import annotations

import os

DEPTH_MONO = 1  # no SGR colour at all (NO_COLOR)
DEPTH_16 = 16
DEPTH_256 = 256
DEPTH_TRUE = 0x1000000  # 24-bit


def rgb(r: int, g: int, b: int) -> int:
    return ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)


def split(color: int) -> tuple[int, int, int]:
    return (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF


# The 16 ANSI base colours as RGB (a common VGA-ish palette).
ANSI_16 = [
    0x000000, 0x800000, 0x008000, 0x808000, 0x000080, 0x800080, 0x008080, 0xC0C0C0,
    0x808080, 0xFF0000, 0x00FF00, 0xFFFF00, 0x0000FF, 0xFF00FF, 0x00FFFF, 0xFFFFFF,
]


def _dist2(a: int, b: int) -> int:
    ar, ag, ab = split(a)
    br, bg, bb = split(b)
    # Weighted (perceptual-ish) squared distance.
    dr, dg, db = ar - br, ag - bg, ab - bb
    return 2 * dr * dr + 4 * dg * dg + 3 * db * db


def rgb_to_16(color: int) -> int:
    """Nearest of the 16 ANSI base colours (index 0-15)."""
    best = 0
    best_d = None
    for i, base in enumerate(ANSI_16):
        d = _dist2(color, base)
        if best_d is None or d < best_d:
            best_d = d
            best = i
    return best


def _cube_component(v: int) -> int:
    """Map one 0-255 channel to a 0-5 xterm cube index."""
    if v < 48:
        return 0
    if v < 115:
        return 1
    return (v - 35) // 40


def rgb_to_256(color: int) -> int:
    """Nearest xterm-256 entry (6x6x6 cube or the grey ramp)."""
    r, g, b = split(color)
    ci = 16 + 36 * _cube_component(r) + 6 * _cube_component(g) + _cube_component(b)
    # Candidate grey from the 24-step ramp.
    grey = round((r + g + b) / 3)
    if grey < 8:
        gi = 232
    elif grey > 238:
        gi = 255
    else:
        gi = 232 + round((grey - 8) / 10)
    # Pick whichever candidate is closer to the real colour.
    cube_rgb = _cube_index_to_rgb(ci)
    grey_val = 8 + 10 * (gi - 232) if gi < 256 else 255
    grey_rgb = rgb(grey_val, grey_val, grey_val)
    return ci if _dist2(color, cube_rgb) <= _dist2(color, grey_rgb) else gi


_CUBE_LEVELS = [0, 95, 135, 175, 215, 255]


def _cube_index_to_rgb(idx: int) -> int:
    idx -= 16
    r = _CUBE_LEVELS[(idx // 36) % 6]
    g = _CUBE_LEVELS[(idx // 6) % 6]
    b = _CUBE_LEVELS[idx % 6]
    return rgb(r, g, b)


def detect_depth(env: dict[str, str] | None = None) -> int:
    """Detect the terminal colour depth from an environment mapping.

    Pure in ``env`` (defaults to ``os.environ``) so it is unit-testable:

    * ``NO_COLOR`` set to a non-empty value -> :data:`DEPTH_MONO` (an empty
      value does not count, per no-color.org);
    * ``STRELKA_COLORS`` / ``TVISION_COLORS`` override wins next;
    * ``COLORTERM`` in ``truecolor``/``24bit`` (or Windows Terminal) -> true;
    * ``TERM`` containing ``256color`` -> 256; a ``dumb`` terminal -> 16;
    * nothing detectable (no ``TERM`` at all) -> truecolor by default.
    """
    env = os.environ if env is None else env
    if env.get("NO_COLOR"):  # present and not empty (no-color.org)
        return DEPTH_MONO
    override = env.get("STRELKA_COLORS") or env.get("TVISION_COLORS")
    if override:
        o = override.strip().lower()
        if o in ("24bit", "truecolor", "true", "16m"):
            return DEPTH_TRUE
        if o == "256":
            return DEPTH_256
        if o == "16":
            return DEPTH_16
        if o in ("mono", "none", "0"):
            return DEPTH_MONO
    ct = (env.get("COLORTERM") or "").lower()
    if ct in ("truecolor", "24bit"):
        return DEPTH_TRUE
    if env.get("WT_SESSION"):  # Windows Terminal
        return DEPTH_TRUE
    term = (env.get("TERM") or "").lower()
    if "256color" in term:
        return DEPTH_256
    if term == "dumb":
        return DEPTH_16
    if term == "":
        return DEPTH_TRUE  # nothing to go on: assume a modern terminal
    return DEPTH_256  # a named terminal we do not recognise


def _luma(color: int) -> int:
    r, g, b = split(color)
    return 299 * r + 587 * g + 114 * b


def sgr(fg: int, bg: int, bold: bool, underline: bool, depth: int) -> str:
    """Build the SGR escape sequence for a cell style.

    In monochrome no colour is sent, so a highlight the theme expresses only
    through colour (a focused or selected row: dark text on a light bar) would
    vanish. There the light/dark relation is kept as an attribute instead: a
    background lighter than the foreground is drawn in reverse video (SGR 7),
    alongside bold and underline.
    """
    parts = ["0"]
    if bold:
        parts.append("1")
    if underline:
        parts.append("4")
    if depth > DEPTH_MONO:
        parts.append(_sgr_color(fg, depth, foreground=True))
        parts.append(_sgr_color(bg, depth, foreground=False))
    elif _luma(bg) > _luma(fg):  # monochrome: attributes only, no colour
        parts.append("7")
    return "\x1b[" + ";".join(parts) + "m"


def _sgr_color(color: int, depth: int, foreground: bool) -> str:
    if depth >= DEPTH_TRUE:
        r, g, b = split(color)
        base = "38" if foreground else "48"
        return f"{base};2;{r};{g};{b}"
    if depth >= DEPTH_256:
        idx = rgb_to_256(color)
        base = "38" if foreground else "48"
        return f"{base};5;{idx}"
    # 16-colour: 30-37 / 90-97 for fg, 40-47 / 100-107 for bg.
    idx = rgb_to_16(color)
    if idx < 8:
        return str((30 if foreground else 40) + idx)
    return str((90 if foreground else 100) + (idx - 8))
