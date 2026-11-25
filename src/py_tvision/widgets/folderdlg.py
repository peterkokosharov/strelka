# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""A modal dialog for choosing a folder (or, optionally, a file).

Built from the existing pieces: a path ``InputLine``, a ``ListBox`` of the
current directory's entries (``..`` then sub-folders then files) with a linked
``ScrollBar``, and OK/Cancel buttons. Folder-only mode (the one Layka needs)
always returns a directory; file mode returns the picked file and may filter by
extension. Navigation is pathlib-based and cross-platform: the top level on
Windows lists the drives, POSIX stops at ``/``, and a directory that cannot be
read shows empty with a note instead of crashing or descending into it.

Keyboard: type in the path line and press Enter to jump, Enter on a folder
descends, Enter on OK returns the choice, Esc cancels. No action is bound to a
function key alone.
"""

from __future__ import annotations

import os
import string
from pathlib import Path

from ..events import Command, Event, EventKind, Mod
from ..geometry import Rect
from ..window import Dialog
from .button import Button
from .inputline import InputLine
from .listbox import ListBox
from .scrollbar import ScrollBar
from .static import Label, StaticText


class _DirList(ListBox):
    """A list box whose Enter descends/selects instead of ending the modal."""

    def __init__(self, bounds: Rect, scrollbar: ScrollBar | None = None):
        super().__init__(bounds, [], scrollbar=scrollbar)
        self.dialog: "FileDialog | None" = None

    def handle_event(self, ev: Event) -> None:
        if (ev.kind == EventKind.KEY and ev.key == "Enter"
                and ev.mods == Mod.NONE and self.dialog is not None):
            self.dialog._activate_entry()
            ev.clear()
            return
        super().handle_event(ev)


class FileDialog(Dialog):
    """Pick a directory (``folders_only``) or a file, under the modal loop."""

    def __init__(self, bounds: Rect, title: str = "Choose folder",
                 start_dir: str | os.PathLike | None = None,
                 folders_only: bool = True,
                 extensions: list[str] | None = None):
        super().__init__(bounds, title)
        self.folders_only = folders_only
        self.extensions = {e.lower() for e in extensions} if extensions else None
        self.result_path: Path | None = None
        self.note = ""
        self.drives_mode = False
        self._entry_list: list[tuple[str, str]] = []  # (kind, name) per list row

        start = Path(start_dir).expanduser() if start_dir is not None else Path.cwd()
        start = self._resolve(start) or start
        # A file (or a path that no longer exists) opens the nearest existing
        # folder above it, so the dialog never starts on a non-directory.
        while not self._is_dir(start) and start.parent != start:
            start = start.parent
        self.cwd: Path = start

        w, h = self.bounds.width, self.bounds.height
        self.path_line = InputLine(Rect(8, 1, w - 2, 2), max_length=1024)
        self.insert(self.path_line)
        self.insert(Label(Rect(2, 1, 8, 2), "~P~ath:", self.path_line))
        self.scrollbar = ScrollBar(Rect(w - 3, 3, w - 2, h - 4))
        self.insert(self.scrollbar)
        self.dir_list = _DirList(Rect(2, 3, w - 3, h - 4), scrollbar=self.scrollbar)
        self.dir_list.dialog = self
        self.insert(self.dir_list)
        self.note_text = StaticText(Rect(2, h - 3, w - 2, h - 2), "", role="dialog.body")
        self.insert(self.note_text)
        self.insert(Button(Rect(w - 22, h - 2, w - 12, h - 1),
                           "O~K~", Command.OK, default=True))
        self.insert(Button(Rect(w - 11, h - 2, w - 2, h - 1),
                           "~C~ancel", Command.CANCEL))
        self.dir_list.focus()
        self._refresh()

    # -- directory listing --------------------------------------------------

    @staticmethod
    def _is_dir(path: Path) -> bool:
        try:
            return path.is_dir()
        except OSError:
            return False

    @staticmethod
    def _is_file(path: Path) -> bool:
        """A regular file that exists now (a dangling symlink is not one).

        ``Path.is_file`` can raise ``PermissionError`` on Python 3.12/3.13,
        so it goes through the same guard as :meth:`_is_dir`.
        """
        try:
            return path.is_file()
        except OSError:
            return False

    @staticmethod
    def _resolve(path: Path) -> Path | None:
        """``path.resolve()``, or ``None`` if the filesystem refuses (a
        symlink loop raises ``RuntimeError`` on older Pythons)."""
        try:
            return path.resolve()
        except (OSError, RuntimeError):
            return None

    def _at_anchor(self) -> bool:
        """True at a filesystem root (a Windows drive root or POSIX ``/``)."""
        return self.cwd.parent == self.cwd

    def _match_file(self, path: Path) -> bool:
        if self.extensions is None:
            return True
        return path.suffix.lower() in self.extensions

    def _drives(self) -> list[Path]:
        # os.listdrives (Windows, Python 3.12+) asks the OS for the drive list
        # without touching each drive; probing 26 letters with exists() can
        # block for a long time on a dead network drive.
        listdrives = getattr(os, "listdrives", None)
        if listdrives is not None:
            try:
                return [Path(d) for d in listdrives()]
            except OSError:
                pass
        out: list[Path] = []
        for letter in string.ascii_uppercase:
            p = Path(f"{letter}:\\")
            if p.exists():
                out.append(p)
        return out

    def _build_entries(self) -> list[str]:
        self._entry_list = []
        display: list[str] = []
        if self.drives_mode:
            for drive in self._drives():
                self._entry_list.append(("drive", str(drive)))
                display.append(str(drive))
            return display
        # ".." to go up, except at a POSIX root.
        if not self._at_anchor() or os.name == "nt":
            self._entry_list.append(("up", ".."))
            display.append("..")
        try:
            children = list(self.cwd.iterdir())
            self.note = ""
        except (PermissionError, OSError):
            self.note = "(permission denied)"
            children = []
        dirs = sorted((c.name for c in children if self._is_dir(c)), key=str.lower)
        for name in dirs:
            self._entry_list.append(("dir", name))
            display.append(name + "/")
        if not self.folders_only:
            files = sorted(
                (c.name for c in children
                 if self._is_file(c) and self._match_file(c)),
                key=str.lower)
            for name in files:
                self._entry_list.append(("file", name))
                display.append(name)
        return display

    def _refresh(self) -> None:
        display = self._build_entries()
        self.dir_list.set_items(display)
        self.path_line.data = "" if self.drives_mode else str(self.cwd)
        self.path_line.cursor_pos = len(self.path_line.data)
        self.path_line.first = 0
        self.note_text.text = self.note
        self.draw_view()

    # -- navigation ---------------------------------------------------------

    def _entry_at(self, index: int) -> tuple[str, str] | None:
        if 0 <= index < len(self._entry_list):
            return self._entry_list[index]
        return None

    def _enter_dir(self, target: Path) -> None:
        # Refuse to descend into something we cannot read.
        try:
            with os.scandir(target):
                pass
        except (PermissionError, OSError):
            self.note = f"Cannot open {target.name or target} (permission denied)"
            self.note_text.text = self.note
            self.draw_view()
            return
        self.cwd = target
        self.drives_mode = False
        self._refresh()

    def _go_up(self) -> None:
        if self.drives_mode:
            return
        if self._at_anchor():
            if os.name == "nt":
                self.drives_mode = True
                self._refresh()
        else:
            self.cwd = self.cwd.parent
            self._refresh()

    def _activate_entry(self) -> None:
        entry = self._entry_at(self.dir_list.focused_index)
        if entry is None:
            return
        kind, name = entry
        if kind == "up":
            self._go_up()
        elif kind == "drive":
            self._enter_dir(Path(name))
        elif kind == "dir":
            self._enter_dir(self.cwd / name)
        elif kind == "file" and not self.folders_only:
            self._choose_file(self.cwd / name)

    def _choose_file(self, path: Path) -> None:
        """Return ``path`` if it is (still) a regular file, else say so."""
        if self._is_file(path) and self._match_file(path):
            self.result_path = path
            self.end_modal(Command.OK)
        else:
            self._show_note("(path not found)")

    def _show_note(self, note: str) -> None:
        self.note = note
        self.note_text.text = note
        self.draw_view()

    def _jump_to_path(self) -> None:
        raw = self.path_line.data.strip()
        if not raw:
            return
        # Relative input ("..", "sub", "~/x") is relative to the folder shown,
        # not to the process working directory; cwd stays absolute.
        target = self._resolve(self.cwd / Path(raw).expanduser())
        if target is None:
            self._show_note("(path not found)")
        elif self._is_dir(target):
            self._enter_dir(target)
        elif not self.folders_only:
            self._choose_file(target)
        else:
            self._show_note("(path not found)")

    # -- confirm / events ---------------------------------------------------

    def _confirm(self) -> None:
        """OK never ends the dialog without a path (that would read as Cancel).

        In the drive list, OK opens the focused drive. In folder mode it returns
        the folder currently browsed. In file mode it returns the focused file;
        on a folder, ``..`` or drive it navigates instead and stays open.
        """
        if self.drives_mode:
            entry = self._entry_at(self.dir_list.focused_index)
            if entry is not None:
                self._activate_entry()
            return
        if self.folders_only:
            self.result_path = self.cwd
            self.end_modal(Command.OK)
            return
        if self._entry_at(self.dir_list.focused_index) is not None:
            self._activate_entry()

    def handle_event(self, ev: Event) -> None:
        if (ev.kind == EventKind.KEY and ev.key == "Enter" and ev.mods == Mod.NONE
                and self.current is self.path_line):
            self._jump_to_path()
            ev.clear()
            return
        super().handle_event(ev)

    def handle_own_command(self, ev: Event) -> None:
        if ev.command == Command.OK:
            self._confirm()
            ev.clear()
            return
        super().handle_own_command(ev)


def _run(program, folders_only: bool, start_dir, title: str,
         extensions: list[str] | None) -> Path | None:
    w, h = program.screen.width, program.screen.height
    width = min(max(40, w - 8), w)
    height = min(max(14, h - 4), h)
    x = max(0, (w - width) // 2)
    y = max(0, (h - height) // 2)
    dlg = FileDialog(Rect(x, y, x + width, y + height), title,
                     start_dir=start_dir, folders_only=folders_only,
                     extensions=extensions)
    result = program.exec_view(dlg)
    if result in (Command.OK, Command.YES):
        return dlg.result_path
    return None


def choose_folder(program, start_dir=None, title: str = "Choose folder") -> Path | None:
    """Modal folder picker; returns the chosen directory or ``None``."""
    return _run(program, True, start_dir, title, None)


def choose_file(program, start_dir=None, title: str = "Choose file",
                extensions: list[str] | None = None) -> Path | None:
    """Modal file picker; returns the chosen file or ``None``."""
    return _run(program, False, start_dir, title, extensions)
