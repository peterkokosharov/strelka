# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Program, Desktop, the main loop, modal exec_view, idle and resize.

The program is the root group: a menu/info bar on top, a desktop in the
middle and a status line at the bottom. ``run`` drives the real terminal;
``exec_view`` runs a nested modal loop until the inserted view calls
``end_modal``. Tests build a program on a :class:`HeadlessTerminal`, drive it
with ``put_event`` / ``pump`` and snapshot the screen buffer.
"""

from __future__ import annotations

import time
from typing import Callable

from .events import Command, Event, EventKind, PostQueue, command_event
from .geometry import Point, Rect
from .screen import DrawContext, Screen
from .theme import Style, Theme, get_theme
from .views import Grow, Group, State, View


class _TerminalGuards:
    """Handles that restore the terminal if the process is killed or crashes.

    Registered by :func:`install_terminal_guards`; the owner calls
    :meth:`uninstall` from its normal ``finally`` once a clean ``stop`` has run.
    """

    __slots__ = ("restore", "uninstall", "handler", "signals")

    def __init__(self, restore, uninstall, handler, signals):
        self.restore = restore
        self.uninstall = uninstall
        self.handler = handler
        self.signals = signals


def _restore_errors() -> tuple[type[BaseException], ...]:
    """Exceptions a terminal restore may raise once the tty is gone (EIO on
    SIGHUP): ``OSError`` plus ``termios.error``, which is not an OSError."""
    errors: list[type[BaseException]] = [OSError]
    try:
        import termios

        errors.append(termios.error)
    except ImportError:  # Windows
        pass
    return tuple(errors)


def install_terminal_guards(terminal, *, atexit_mod=None, signal_mod=None,
                            os_mod=None) -> _TerminalGuards:
    """Guarantee the terminal is restored on ``atexit`` and on fatal signals.

    A killed or crashing process must not leave the tty in raw/alt-screen mode
    with the cursor hidden. We register an ``atexit`` handler plus a handler for
    ``SIGTERM`` (and ``SIGHUP`` where it exists; neither is guaranteed on
    Windows) that restores cooked mode, the main screen and the cursor by
    calling ``terminal.stop()`` -- which is idempotent.

    After restoring, the signal is passed on: if the previous disposition was a
    Python callable it is called (chaining), otherwise the default disposition
    is put back and the signal re-raised so the exit status is still correct.
    A signal that is ignored (``SIG_IGN``, e.g. under ``nohup``) or handled
    from C (``getsignal`` returns ``None``) is left alone. A restore that fails
    because the tty is already gone is swallowed so it can neither mask the
    signal nor crash ``atexit``.

    The module dependencies are injectable so the registration is unit-testable
    without a real terminal or actually killing the process.
    """
    import atexit as _atexit
    import os as _os
    import signal as _signal

    atexit_mod = atexit_mod or _atexit
    signal_mod = signal_mod or _signal
    os_mod = os_mod or _os
    restore_errors = _restore_errors()

    def restore(*_a) -> None:
        try:
            terminal.stop()  # idempotent: safe after a clean stop or a second call
        except restore_errors:
            pass  # the tty is gone (EIO after SIGHUP); nothing left to restore

    atexit_mod.register(restore)

    previous: dict = {}

    def handler(signum, frame=None) -> None:
        restore()
        prev = previous.get(signum, signal_mod.SIG_DFL)
        if callable(prev) and prev not in (signal_mod.SIG_DFL, signal_mod.SIG_IGN):
            prev(signum, frame)  # the application's own handler decides
            return
        # Re-raise with the default action so we do not swallow the signal.
        try:
            signal_mod.signal(signum, signal_mod.SIG_DFL)
        except (ValueError, OSError):
            pass
        os_mod.kill(os_mod.getpid(), signum)

    signals: list = []
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal_mod, name, None)
        if sig is None:
            continue  # e.g. SIGHUP does not exist on Windows
        try:
            current = signal_mod.getsignal(sig)
        except (ValueError, OSError):
            continue
        if current is None or current == signal_mod.SIG_IGN:
            continue  # handled from C, or deliberately ignored (nohup): keep it
        try:
            previous[sig] = signal_mod.signal(sig, handler)
            signals.append(sig)
        except (ValueError, OSError):
            pass  # not in the main thread, or unsupported

    def uninstall() -> None:
        try:
            atexit_mod.unregister(restore)
        except Exception:
            pass
        for sig in signals:
            prev = previous.get(sig, signal_mod.SIG_DFL)
            if prev is None:
                continue  # cannot be re-installed from Python
            try:
                signal_mod.signal(sig, prev)
            except (ValueError, OSError, TypeError):
                pass

    return _TerminalGuards(restore, uninstall, handler, signals)


class Desktop(Group):
    def __init__(self, bounds: Rect):
        super().__init__(bounds)
        self.grow_mode = Grow.HI_X | Grow.HI_Y

    def draw_background(self, ctx: DrawContext) -> None:
        style = self.get_style("desktop")
        # A faint checkerboard, like the classic Turbo Vision backdrop.
        for y in range(self.bounds.height):
            for x in range(self.bounds.width):
                ctx.put(x, y, "░", style)


class Program(Group):
    def __init__(self, terminal, theme: str | Theme = "classic"):
        self.terminal = terminal
        w, h = terminal.size()
        super().__init__(Rect(0, 0, w, h))
        self.the_theme: Theme = theme if isinstance(theme, Theme) else get_theme(theme)
        self.screen = Screen(w, h, depth=getattr(terminal, "depth", 0x1000000),
                             default_style=self.the_theme.style("desktop"))
        self.running = False
        self.menu_popup = None
        self.post_queue = PostQueue(wake=getattr(terminal, "wake", None))
        self._clipboard = ""
        self.idle_handlers: list[Callable[[], None]] = []
        self._timers: list[list] = []  # [interval, next_time, fn]

        self.menubar: View | None = None
        self.status_line: View | None = None
        self.desktop = Desktop(Rect(0, 1, w, h - 1))
        self.insert(self.desktop)
        self.state |= State.FOCUSED | State.ACTIVE
        self.focus_child(self.desktop)

    # -- composition --------------------------------------------------------

    def set_menu_bar(self, bar: View) -> None:
        bar.grow_mode = Grow.HI_X
        self.menubar = bar
        self.insert(bar)

    def set_status_line(self, line: View) -> None:
        line.grow_mode = Grow.LO_Y | Grow.HI_Y | Grow.HI_X
        self.status_line = line
        self.insert(line)

    def draw_background(self, ctx: DrawContext) -> None:
        ctx.fill(Rect(0, 0, self.bounds.width, self.bounds.height), " ",
                 self.get_style("desktop"))

    def draw(self, ctx: DrawContext) -> None:
        super().draw(ctx)
        box = self.menu_popup
        if box is not None:
            corigin = Point(ctx.origin.x + box.bounds.x1, ctx.origin.y + box.bounds.y1)
            cclip = box.abs_bounds().intersect(ctx.clip)
            if not cclip.is_empty():
                box.draw(DrawContext(ctx.buffer, corigin, cclip))

    # -- event entry points -------------------------------------------------

    def handle_event(self, ev: Event) -> None:
        if self.menu_popup is not None and self.menubar is not None and ev.kind in (
            EventKind.KEY, EventKind.MOUSE_DOWN, EventKind.MOUSE_UP, EventKind.MOUSE_MOVE,
        ):
            self.menubar.handle_event(ev)
            if ev.handled:
                return
        super().handle_event(ev)

    def handle_own_command(self, ev: Event) -> None:
        if ev.command == Command.QUIT:
            self.running = False
            ev.clear()

    def put_event(self, ev: Event) -> None:
        self.post_queue.post(ev)

    def post(self, item) -> None:
        """Thread-safe: hand an event or callable to the UI thread."""
        self.post_queue.post(item)

    # -- clipboard ----------------------------------------------------------

    def set_clipboard(self, text: str) -> None:
        self._clipboard = text
        setter = getattr(self.terminal, "set_clipboard", None)
        if setter is not None:
            setter(text)

    def get_clipboard(self) -> str:
        return self._clipboard

    # -- timers / idle ------------------------------------------------------

    def every(self, interval: float, fn: Callable[[], None]) -> None:
        self._timers.append([interval, time.monotonic() + interval, fn])

    def idle(self) -> None:
        for fn in list(self.idle_handlers):
            fn()
        now = time.monotonic()
        for timer in self._timers:
            if now >= timer[1]:
                timer[1] = now + timer[0]
                timer[2]()

    # -- drawing / cursor ---------------------------------------------------

    def focused_leaf(self) -> View:
        node: View = self
        while isinstance(node, Group) and node.current is not None:
            node = node.current
        return node

    def _update_cursor(self) -> None:
        leaf = self.focused_leaf()
        cur = getattr(leaf, "cursor", None)
        if cur is not None and (leaf.state & State.VISIBLE):
            o = leaf.abs_origin()
            self.screen.cursor = Point(o.x + cur.x, o.y + cur.y)
        else:
            self.screen.cursor = None

    def redraw(self) -> None:
        self.draw(self.screen.context())
        self._update_cursor()
        out = self.screen.flush()
        cursor = self.screen.cursor
        tail = ""
        if cursor is not None:
            tail = f"\x1b[{cursor.y + 1};{cursor.x + 1}H\x1b[?25h"
        elif out:
            tail = "\x1b[?25l"
        if out or tail:
            self.terminal.write(out + tail)

    # -- loop ---------------------------------------------------------------

    def _next_timeout(self) -> float | None:
        if self._timers:
            now = time.monotonic()
            return max(0.0, min(t[1] - now for t in self._timers))
        if self.idle_handlers:
            return 0.05
        return None

    def pump(self, timeout: float | None = 0.0) -> bool:
        """Run one turn: redraw, read and dispatch a batch. Returns False when
        no events were available (the caller may stop in headless mode)."""
        if self.screen.dirty:
            self.redraw()
        posted = self.post_queue.drain()
        events = self.terminal.read(0 if posted else timeout)
        batch = posted + events
        if not batch:
            self.idle()
            return False
        for item in batch:
            if callable(item):
                item()
            else:
                self._dispatch(item)
        return True

    def _dispatch(self, ev: Event) -> None:
        if ev.kind == EventKind.RESIZE and ev.info:
            w, h = ev.info
            self.resize(w, h)
            return
        self.handle_event(ev)

    def resize(self, width: int, height: int) -> None:
        self.screen.resize(width, height)
        self.change_bounds(Rect(0, 0, width, height))
        self.screen.dirty = True

    def run(self) -> None:
        # Guard first: if start() or the loop dies, atexit/SIGTERM still restore
        # the terminal. Restore is idempotent, so the finally below and the
        # atexit handler calling it twice is harmless.
        guards = install_terminal_guards(self.terminal)
        try:
            # Inside the try: if start() raises, stop() still undoes whatever
            # part of it ran and the guards are uninstalled.
            self.terminal.start()
            self.running = True
            self.screen.dirty = True
            while self.running:
                self.pump(self._next_timeout())
        finally:
            self.terminal.stop()
            guards.uninstall()

    # -- modal --------------------------------------------------------------

    def exec_view(self, view) -> int:
        self.desktop.insert(view)
        view.set_state(State.ACTIVE, True)
        self.desktop.focus_child(view)
        self.screen.dirty = True
        result: int | None = None
        try:
            while True:
                r = getattr(view, "_modal_result", None)
                if r is not None:
                    result = r
                    break
                had = self.pump(self._next_timeout() if not self.terminal.is_headless else 0.0)
                if not had and self.terminal.is_headless:
                    break  # no more scripted input in a test; avoid hanging
                if not self.running and not self.terminal.is_headless:
                    break
        finally:
            self.desktop.remove(view)
            view.set_state(State.ACTIVE, False)
            self.screen.dirty = True
        return result if result is not None else Command.CANCEL


class Application(Program):
    """Convenience base class; subclass and build the UI in ``setup``."""

    def __init__(self, terminal, theme: str | Theme = "classic"):
        super().__init__(terminal, theme)
        self.setup()

    def setup(self) -> None:  # pragma: no cover - overridden by apps
        pass
