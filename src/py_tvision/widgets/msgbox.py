# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Modal message box."""

from __future__ import annotations

from ..events import Command
from ..geometry import Rect
from ..text import parse_hotkey, str_width
from ..window import Dialog
from .button import Button
from .static import StaticText

OK = [("O~K~", Command.OK)]
OK_CANCEL = [("O~K~", Command.OK), ("~C~ancel", Command.CANCEL)]
YES_NO = [("~Y~es", Command.YES), ("~N~o", Command.NO)]


def build_message_box(screen_w: int, screen_h: int, text: str, title: str,
                      buttons: list[tuple[str, int]]) -> Dialog:
    """Build (but do not run) a message-box dialog. Useful for snapshot tests."""
    lines = text.split("\n")
    text_w = max((str_width(line) for line in lines), default=0)
    btn_labels = [parse_hotkey(b[0])[0] for b in buttons]
    btn_w = sum(str_width(lbl) + 4 for lbl in btn_labels) + 2
    width = max(text_w + 6, btn_w + 4, str_width(title) + 6, 24)
    width = min(width, screen_w)
    height = len(lines) + 6
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    dlg = Dialog(Rect(x, y, x + width, y + height), title)

    for i, line in enumerate(lines):
        dlg.insert(StaticText(Rect(2, 1 + i, width - 2, 2 + i), line, role="dialog.body"))

    # Lay the buttons out centred on the second-to-last row.
    total = sum(str_width(lbl) + 4 for lbl in btn_labels) + (len(buttons) - 1)
    bx = max(2, (width - total) // 2)
    by = height - 2
    for (label, command), disp in zip(buttons, btn_labels):
        bw = str_width(disp) + 4
        dlg.insert(Button(Rect(bx, by, bx + bw, by + 1), label, command,
                          default=(command in (Command.OK, Command.YES))))
        bx += bw + 1
    return dlg


def message_box(program, text: str, title: str = "Message",
                buttons: list[tuple[str, int]] | None = None) -> int:
    """Show a modal message box and return the command that closed it."""
    buttons = buttons or OK
    w, h = program.screen.width, program.screen.height
    dlg = build_message_box(w, h, text, title, buttons)
    return program.exec_view(dlg)
