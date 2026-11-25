#!/usr/bin/env python3
# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""py_tvision phase-1 demo.

A desktop with one window, a menu bar (File: New window / Dialog... / Exit;
Help: About), a status line, and a dialog containing a labelled input line, a
list box with a scroll bar and OK/Cancel buttons. Mouse clicks and resize
work.

Run it (from the repository):

    python examples/demo.py                 # pick the theme from STRELKA_THEME
    python examples/demo.py --theme modern

Keys:  F10 or Alt-F / Alt-H open menus,  Tab moves focus,  Alt-X exits,
       Esc closes a dialog or menu.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from py_tvision import CMD_USER, Application, Command, Event, Rect  # noqa: E402
from py_tvision.color import detect_depth  # noqa: E402
from py_tvision.platform import open_terminal  # noqa: E402
from py_tvision.views import Grow, State  # noqa: E402
from py_tvision.widgets import (  # noqa: E402
    Button,
    CheckBoxes,
    ComboBox,
    InputLine,
    Label,
    Memo,
    MenuBar,
    MenuItem,
    RadioButtons,
    Spinner,
    StaticText,
    StatusItem,
    StatusLine,
    SubMenu,
    choose_folder,
    message_box,
)
from py_tvision.widgets.msgbox import OK  # noqa: E402
from py_tvision.window import Window  # noqa: E402

CM_NEW_WINDOW = CMD_USER + 1
CM_DIALOG = CMD_USER + 2
CM_ABOUT = CMD_USER + 3
CM_FOLDER = CMD_USER + 4


class DemoApp(Application):
    def setup(self) -> None:
        w, h = self.screen.width, self.screen.height

        menu = MenuBar(Rect(0, 0, w, 1), [
            SubMenu("~F~ile", [
                MenuItem("~N~ew window", CM_NEW_WINDOW),
                MenuItem("~D~ialog...", CM_DIALOG),
                MenuItem("Choose ~f~older...", CM_FOLDER),
                MenuItem("-"),
                MenuItem("E~x~it", Command.QUIT),
            ]),
            SubMenu("~H~elp", [
                MenuItem("~A~bout", CM_ABOUT),
            ]),
        ])
        self.set_menu_bar(menu)

        status = StatusLine(Rect(0, h - 1, w, h), [
            StatusItem("~F1~ Help", "F1", CM_ABOUT),
            StatusItem("~F2~ Dialog", "F2", CM_DIALOG),
            StatusItem("~Alt-X~ Exit", "Alt+X", Command.QUIT),
        ])
        self.set_status_line(status)

        self.new_window("Welcome")

    def new_window(self, title: str) -> None:
        w, h = self.screen.width, self.screen.height
        win = Window(Rect(4, 3, w - 6, h - 4), title)
        win.grow_mode = Grow.HI_X | Grow.HI_Y
        win.insert(StaticText(
            Rect(2, 2, win.bounds.width - 2, 8),
            "py_tvision demo.\n\n"
            "Open File -> Dialog... (or press F2) for a dialog\n"
            "with an input line and a list box.\n\n"
            "Alt-X or File -> Exit quits.",
            role="window",
        ))
        self.desktop.insert(win)
        win.set_state(State.ACTIVE, True)
        self.desktop.focus_child(win)
        self.screen.dirty = True

    def open_dialog(self) -> None:
        dlg = _make_dialog(self, 56, 20)
        result = self.exec_view(dlg)
        if result == Command.OK:
            opts = ", ".join(dlg.checks.items[i][0] for i in sorted(dlg.checks.value)) or "none"
            message_box(
                self,
                f"Name: {dlg.input.data}\n"
                f"Count: {dlg.count.value}\n"
                f"Colour: {dlg.colour.value}\n"
                f"Mode: {dlg.mode.selected_label()}\n"
                f"Options: {opts}",
                "Result", OK,
            )

    def choose_folder_cmd(self) -> None:
        path = choose_folder(self, title="Pick a folder")
        if path is not None:
            message_box(self, f"You chose:\n{path}", "Folder", OK)

    def handle_own_command(self, ev: Event) -> None:
        if ev.command == CM_NEW_WINDOW:
            self.new_window("Window")
            ev.clear()
        elif ev.command == CM_FOLDER:
            ev.clear()
            self.choose_folder_cmd()
        elif ev.command == CM_DIALOG:
            ev.clear()
            self.open_dialog()
        elif ev.command == CM_ABOUT:
            ev.clear()
            message_box(
                self,
                "py_tvision\nphase-1 demo\n\nMIT, Peter Kokosharov",
                "About", OK,
            )
        else:
            super().handle_own_command(ev)


def _make_dialog(app, width, height):  # pragma: no cover - exercised interactively
    from py_tvision.window import Dialog

    w, h = app.screen.width, app.screen.height
    x = (w - width) // 2
    y = (h - height) // 2
    dlg = Dialog(Rect(x, y, x + width, y + height), "Form widgets")

    inp = InputLine(Rect(10, 2, 30, 3), max_length=80, text="hello")
    dlg.insert(inp)
    dlg.insert(Label(Rect(2, 2, 10, 3), "~N~ame:", inp))

    pwd = InputLine(Rect(10, 3, 30, 4), max_length=80, password=True)
    dlg.insert(pwd)
    dlg.insert(Label(Rect(2, 3, 10, 4), "~P~ass:", pwd))

    count = Spinner(Rect(10, 4, 20, 5), value=3, minimum=0, maximum=99, step=1)
    dlg.insert(count)
    dlg.insert(Label(Rect(2, 4, 10, 5), "~C~ount:", count))

    colour = ComboBox(Rect(10, 5, 30, 6), ["red", "green", "blue", "cyan"], index=1)
    dlg.insert(colour)
    dlg.insert(Label(Rect(2, 5, 10, 6), "Co~l~our:", colour))

    dlg.insert(Label(Rect(width - 24, 1, width - 2, 2), "Options:"))
    checks = CheckBoxes(Rect(width - 24, 2, width - 2, 6),
                        ["~B~old", "~I~talic", "~U~nderline"], checked={0})
    dlg.insert(checks)

    dlg.insert(Label(Rect(width - 24, 7, width - 2, 8), "Mode:"))
    mode = RadioButtons(Rect(width - 24, 8, width - 2, 12),
                        ["~F~ast", "~S~afe", "~D~ry run"], selected=1)
    dlg.insert(mode)

    dlg.insert(Label(Rect(2, 7, 10, 8), "No~t~es:"))
    memo = Memo(Rect(2, 8, 30, height - 3),
                "Multi-line memo.\nArrows move, Enter splits.")
    dlg.insert(memo)

    dlg.insert(Button(Rect(width - 22, height - 2, width - 12, height - 1),
                      "O~K~", Command.OK, default=True))
    dlg.insert(Button(Rect(width - 11, height - 2, width - 2, height - 1),
                      "~C~ancel", Command.CANCEL))
    dlg.input = inp  # type: ignore[attr-defined]
    dlg.count = count  # type: ignore[attr-defined]
    dlg.colour = colour  # type: ignore[attr-defined]
    dlg.checks = checks  # type: ignore[attr-defined]
    dlg.mode = mode  # type: ignore[attr-defined]
    dlg.memo = memo  # type: ignore[attr-defined]
    return dlg


def main() -> int:
    theme = "classic"
    if "--theme" in sys.argv:
        theme = sys.argv[sys.argv.index("--theme") + 1]
    elif os.environ.get("STRELKA_THEME"):
        theme = os.environ["STRELKA_THEME"]

    terminal = open_terminal()
    terminal.depth = detect_depth()
    app = DemoApp(terminal, theme=theme)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
