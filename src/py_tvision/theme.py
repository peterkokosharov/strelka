# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Styles, roles and built-in themes.

A ``Style`` is a frozen (hashable) value so screen rows can be compared with
a plain list equality in the diff, and so identical styles intern naturally.
A theme maps role names (strings) to styles; widgets ask for a role and may
override roles locally. Colour values here are our own, never copied from
Borland's palette byte strings.
"""

from __future__ import annotations

from dataclasses import dataclass

from .color import rgb


@dataclass(frozen=True)
class Style:
    fg: int = 0xC0C0C0
    bg: int = 0x000000
    bold: bool = False
    underline: bool = False

    def with_fg(self, fg: int) -> "Style":
        return Style(fg, self.bg, self.bold, self.underline)

    def with_bg(self, bg: int) -> "Style":
        return Style(self.fg, bg, self.bold, self.underline)


DEFAULT_STYLE = Style()


class Theme:
    """A named table of role -> Style with a safe fallback."""

    def __init__(self, name: str, roles: dict[str, Style], fallback: Style = DEFAULT_STYLE):
        self.name = name
        self.roles = dict(roles)
        self.fallback = fallback

    def style(self, role: str) -> Style:
        """Return the style for a role, falling back from ``a.b.c`` to ``a.b``.

        ``window.frame.active`` tries that exact role, then ``window.frame``,
        then ``window``, then the theme default.
        """
        parts = role.split(".")
        while parts:
            key = ".".join(parts)
            if key in self.roles:
                return self.roles[key]
            parts.pop()
        return self.fallback


def _classic() -> Theme:
    blue = rgb(0, 0, 170)
    cyan = rgb(0, 170, 170)
    grey = rgb(170, 170, 170)
    dgrey = rgb(85, 85, 85)
    white = rgb(255, 255, 255)
    yellow = rgb(255, 255, 85)
    black = rgb(0, 0, 0)
    green = rgb(0, 170, 0)
    return Theme(
        "classic",
        {
            "desktop": Style(cyan, blue),
            "window": Style(white, grey),
            "window.frame": Style(white, grey),
            "window.frame.active": Style(white, grey, bold=True),
            "window.title": Style(white, grey, bold=True),
            "dialog": Style(black, grey),
            "dialog.body": Style(black, grey),
            "label": Style(black, grey),
            "label.hotkey": Style(yellow, grey, bold=True),
            "static": Style(black, grey),
            "button": Style(white, green),
            "button.default": Style(white, green, bold=True),
            "button.focused": Style(black, rgb(0, 255, 0), bold=True),
            "button.hotkey": Style(yellow, green, bold=True),
            "button.shadow": Style(dgrey, black),
            "input": Style(black, white),
            "input.focused": Style(black, white),
            "input.selected": Style(white, blue),
            "input.arrow": Style(green, white),
            "list": Style(black, cyan),
            "list.focused": Style(white, blue, bold=True),
            "list.selected": Style(white, blue),
            "scrollbar": Style(black, cyan),
            "scrollbar.arrow": Style(white, cyan, bold=True),
            "menu": Style(black, grey),
            "menu.selected": Style(white, green),
            "menu.hotkey": Style(rgb(170, 0, 0), grey),
            "menu.disabled": Style(dgrey, grey),
            "menubox": Style(black, grey),
            "menubox.selected": Style(white, green),
            "status": Style(black, grey),
            "status.selected": Style(white, green),
            "status.hotkey": Style(rgb(170, 0, 0), grey),
            "shadow": Style(dgrey, black),
            "frame.icon": Style(white, grey, bold=True),
        },
        fallback=Style(grey, blue),
    )


def _modern() -> Theme:
    slate = rgb(30, 34, 42)
    panel = rgb(44, 49, 60)
    text = rgb(220, 223, 228)
    dim = rgb(120, 126, 136)
    accent = rgb(80, 160, 250)
    accent_bg = rgb(0, 0, 175)
    white = rgb(255, 255, 255)
    yellow = rgb(240, 200, 90)
    black = rgb(0, 0, 0)
    sel = rgb(38, 79, 120)
    return Theme(
        "modern",
        {
            "desktop": Style(dim, slate),
            "window": Style(text, panel),
            "window.frame": Style(dim, panel),
            "window.frame.active": Style(accent, panel, bold=True),
            "window.title": Style(text, panel, bold=True),
            "dialog": Style(text, panel),
            "dialog.body": Style(text, panel),
            "label": Style(text, panel),
            "label.hotkey": Style(yellow, panel, bold=True),
            "static": Style(text, panel),
            "button": Style(white, sel),
            "button.default": Style(white, accent_bg, bold=True),
            "button.focused": Style(black, accent, bold=True),
            "button.hotkey": Style(yellow, sel, bold=True),
            "button.shadow": Style(rgb(20, 22, 27), slate),
            "input": Style(white, accent_bg),
            "input.focused": Style(white, accent_bg),
            "input.selected": Style(black, text),
            "input.arrow": Style(accent, accent_bg),
            "list": Style(text, panel),
            "list.focused": Style(white, sel, bold=True),
            "list.selected": Style(white, sel),
            "scrollbar": Style(dim, panel),
            "scrollbar.arrow": Style(accent, panel, bold=True),
            "menu": Style(text, panel),
            "menu.selected": Style(black, accent),
            "menu.hotkey": Style(yellow, panel),
            "menu.disabled": Style(dim, panel),
            "menubox": Style(text, panel),
            "menubox.selected": Style(black, accent),
            "status": Style(text, panel),
            "status.selected": Style(black, accent),
            "status.hotkey": Style(yellow, panel),
            "shadow": Style(rgb(20, 22, 27), slate),
            "frame.icon": Style(accent, panel, bold=True),
        },
        fallback=Style(text, slate),
    )


def _mono() -> Theme:
    white = rgb(255, 255, 255)
    black = rgb(0, 0, 0)
    return Theme(
        "mono",
        {
            "desktop": Style(white, black),
            "window": Style(white, black),
            "window.frame.active": Style(white, black, bold=True),
            "window.title": Style(white, black, bold=True),
            "dialog": Style(white, black),
            "button.focused": Style(black, white),
            "button.default": Style(white, black, bold=True),
            "input": Style(white, black, underline=True),
            "input.selected": Style(black, white),
            "list.focused": Style(black, white),
            "list.selected": Style(black, white, bold=True),
            "menu.selected": Style(black, white),
            "status.selected": Style(black, white),
            "label.hotkey": Style(white, black, bold=True),
            "button.hotkey": Style(white, black, bold=True),
            "menu.hotkey": Style(white, black, bold=True),
            "status.hotkey": Style(white, black, bold=True),
        },
        fallback=Style(white, black),
    )


THEMES = {"classic": _classic, "modern": _modern, "mono": _mono}


def get_theme(name: str) -> Theme:
    factory = THEMES.get(name, _classic)
    return factory()
