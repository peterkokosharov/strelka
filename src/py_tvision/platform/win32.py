# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Windows console backend (ctypes), plus a pure key-record decoder.

The decoder, :func:`decode_key_record`, is a pure function of the fields of a
``KEY_EVENT_RECORD`` and therefore runs and is tested on every OS; only the
reader that pulls real ``INPUT_RECORD``s off the console needs Windows. VT
output is enabled with ``ENABLE_VIRTUAL_TERMINAL_PROCESSING``; if that cannot
be turned on we refuse (a legacy console is an explicit non-goal).

Parts of the console-mode handling follow ideas in magiblot/tvision's
``win32con.cpp`` (Copyright 2019-2025 magiblot, MIT); no code is translated.
"""

from __future__ import annotations

import sys

from ..color import detect_depth
from ..events import (
    EventKind,
    Event,
    MB_LEFT,
    MB_MIDDLE,
    MB_RIGHT,
    Mod,
    key_event,
    mouse_event,
    resize_event,
)

# dwControlKeyState bits.
RIGHT_ALT_PRESSED = 0x0001
LEFT_ALT_PRESSED = 0x0002
RIGHT_CTRL_PRESSED = 0x0004
LEFT_CTRL_PRESSED = 0x0008
SHIFT_PRESSED = 0x0010

# Virtual key codes -> key names.
_VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Esc",
    0x21: "PageUp", 0x22: "PageDown", 0x23: "End", 0x24: "Home",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2D: "Insert", 0x2E: "Delete",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5", 0x75: "F6",
    0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10", 0x7A: "F11", 0x7B: "F12",
}


def utf16_units(text: str) -> int:
    """Number of UTF-16 code *units* in ``text``.

    ``WriteConsoleW`` counts UTF-16 units, not Python code points. A non-BMP
    character (e.g. an emoji, U+1F600) is one code point but two UTF-16 units,
    so passing ``len(text)`` would write short and truncate the frame tail.
    ``surrogatepass`` keeps a lone surrogate (legal in Windows file names, see
    PEP 529) countable as one unit instead of raising and killing the frame.
    """
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def write_console_w(k32, handle, text: str, written_ref) -> int:
    """Call ``k32.WriteConsoleW`` with the correct UTF-16 unit count.

    Factored out of :meth:`Win32Terminal.write` so the length computation is
    testable headlessly with a fake ``k32`` that records the length it was
    handed (a real console is unreachable in the test environment).
    """
    return k32.WriteConsoleW(handle, text, utf16_units(text), written_ref, None)


def decode_key_record(vk: int, unicode_char: str, control_key_state: int,
                      key_down: bool = True) -> Event | None:
    """Decode one KEY_EVENT_RECORD into an Event (or None to ignore it).

    * key-up records are ignored (dead keys/Alt-numpad still deliver text on
      key-down in practice for our subset);
    * AltGr (Right-Alt + Left-Ctrl) yields the produced character, not Alt;
    * Alt+letter is recognised by the (Latin) virtual key, so it works under
      Cyrillic/Greek layouts.
    """
    if not key_down:
        return None

    right_alt = bool(control_key_state & RIGHT_ALT_PRESSED)
    left_alt = bool(control_key_state & LEFT_ALT_PRESSED)
    right_ctrl = bool(control_key_state & RIGHT_CTRL_PRESSED)
    left_ctrl = bool(control_key_state & LEFT_CTRL_PRESSED)
    shift = bool(control_key_state & SHIFT_PRESSED)

    is_altgr = right_alt and left_ctrl
    alt = (left_alt or right_alt) and not is_altgr
    ctrl = (left_ctrl or right_ctrl) and not is_altgr

    mods = Mod.NONE
    if shift:
        mods |= Mod.SHIFT
    if alt:
        mods |= Mod.ALT
    if ctrl:
        mods |= Mod.CTRL

    # AltGr composed character (e.g. non-Latin layouts): deliver the text.
    if is_altgr and unicode_char and unicode_char >= " ":
        return key_event(unicode_char.upper() if unicode_char.isalpha() else unicode_char,
                          Mod.SHIFT if shift else Mod.NONE, text=unicode_char)

    # Named navigation / function keys.
    name = _VK_NAMES.get(vk)
    if name is not None:
        return key_event(name, mods)

    # Alt+letter / Ctrl+letter by virtual key (layout independent).
    if 0x41 <= vk <= 0x5A and (alt or ctrl):
        return key_event(chr(vk), mods)

    # Printable character.
    if unicode_char and unicode_char >= " " and unicode_char != "\x7f":
        name = unicode_char.upper() if (len(unicode_char) == 1 and unicode_char.isalpha()) else unicode_char
        # Keep the Alt modifier (Alt+symbol), drop a bare shift into the text.
        keep = Mod.ALT if alt else Mod.NONE
        return key_event(name, keep, text=unicode_char)

    return None


def _decode_mouse_record(mouse_x: int, mouse_y: int, button_state: int,
                         control_key_state: int, event_flags: int) -> Event | None:
    MOUSE_MOVED = 0x0001
    DOUBLE_CLICK = 0x0002
    MOUSE_WHEELED = 0x0004
    mods = Mod.NONE
    if control_key_state & SHIFT_PRESSED:
        mods |= Mod.SHIFT
    if control_key_state & (LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED):
        mods |= Mod.ALT
    if control_key_state & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED):
        mods |= Mod.CTRL
    buttons = 0
    if button_state & 0x0001:
        buttons |= MB_LEFT
    if button_state & 0x0002:
        buttons |= MB_RIGHT
    if button_state & 0x0004:
        buttons |= MB_MIDDLE
    if event_flags & MOUSE_WHEELED:
        # High word of button_state is signed wheel delta.
        delta = (button_state >> 16) & 0xFFFF
        if delta >= 0x8000:
            delta -= 0x10000
        return mouse_event(EventKind.MOUSE_WHEEL, mouse_x, mouse_y,
                           wheel=1 if delta > 0 else -1, mods=mods)
    if event_flags & MOUSE_MOVED:
        return mouse_event(EventKind.MOUSE_MOVE, mouse_x, mouse_y, buttons=buttons, mods=mods)
    if buttons:
        return mouse_event(EventKind.MOUSE_DOWN, mouse_x, mouse_y, buttons=buttons, mods=mods)
    return mouse_event(EventKind.MOUSE_UP, mouse_x, mouse_y, mods=mods)


class Win32Terminal:
    """Real Windows console terminal. Only constructed on win32."""

    is_headless = False

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32Terminal is only available on Windows")
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._k32 = ctypes.windll.kernel32
        self._hin = self._k32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        self._hout = self._k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        self._old_in_mode = wintypes.DWORD()
        self._old_out_mode = wintypes.DWORD()
        self._old_in_cp = self._k32.GetConsoleCP()
        self._old_out_cp = self._k32.GetConsoleOutputCP()
        self._wake_event = self._k32.CreateEventW(None, False, False, None)
        self._decoder = None  # set if VT input is ever enabled
        self._started = False
        self.depth = detect_depth()

    def start(self) -> None:
        k32 = self._k32
        wintypes = self._wintypes
        if not k32.GetConsoleMode(self._hin, self._ctypes.byref(self._old_in_mode)):
            raise RuntimeError("standard input is not a console")
        if not k32.GetConsoleMode(self._hout, self._ctypes.byref(self._old_out_mode)):
            raise RuntimeError("standard output is not a console")
        ENABLE_WINDOW_INPUT = 0x0008
        ENABLE_MOUSE_INPUT = 0x0010
        ENABLE_EXTENDED_FLAGS = 0x0080
        new_in = ENABLE_WINDOW_INPUT | ENABLE_MOUSE_INPUT | ENABLE_EXTENDED_FLAGS
        k32.SetConsoleMode(self._hin, wintypes.DWORD(new_in))
        ENABLE_PROCESSED_OUTPUT = 0x0001
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        DISABLE_NEWLINE_AUTO_RETURN = 0x0008
        new_out = (ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                   | DISABLE_NEWLINE_AUTO_RETURN)
        if not k32.SetConsoleMode(self._hout, wintypes.DWORD(new_out)):
            self.stop()
            raise RuntimeError("cannot enable virtual terminal output (legacy console)")
        k32.SetConsoleCP(65001)
        k32.SetConsoleOutputCP(65001)
        self.write("\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1006h")
        self._started = True

    def stop(self) -> None:
        if self._started:
            self.write("\x1b[?1006l\x1b[?1000l\x1b[?25h\x1b[?1049l")
        self._k32.SetConsoleMode(self._hin, self._old_in_mode)
        self._k32.SetConsoleMode(self._hout, self._old_out_mode)
        self._k32.SetConsoleCP(self._old_in_cp)
        self._k32.SetConsoleOutputCP(self._old_out_cp)
        self._started = False

    def size(self) -> tuple[int, int]:
        import ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

        class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                        ("wAttributes", ctypes.c_ushort), ("srWindow", SMALL_RECT),
                        ("dwMaximumWindowSize", COORD)]

        info = CONSOLE_SCREEN_BUFFER_INFO()
        if self._k32.GetConsoleScreenBufferInfo(self._hout, ctypes.byref(info)):
            w = info.srWindow.Right - info.srWindow.Left + 1
            h = info.srWindow.Bottom - info.srWindow.Top + 1
            return max(1, w), max(1, h)
        return 80, 25

    def read(self, timeout: float | None) -> list[Event]:
        import ctypes

        ms = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        handles = (ctypes.c_void_p * 2)(self._hin, self._wake_event)
        WAIT_TIMEOUT = 0x102
        rc = self._k32.WaitForMultipleObjects(2, handles, False, ms)
        if rc == WAIT_TIMEOUT or rc == (0 + 1):  # wake event signalled
            return []
        return self._read_pending()

    def _read_pending(self) -> list[Event]:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class KEY_EVENT_RECORD(ctypes.Structure):
            _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", ctypes.c_ushort),
                        ("wVirtualKeyCode", ctypes.c_ushort),
                        ("wVirtualScanCode", ctypes.c_ushort),
                        ("UnicodeChar", ctypes.c_wchar),
                        ("dwControlKeyState", wintypes.DWORD)]

        class MOUSE_EVENT_RECORD(ctypes.Structure):
            _fields_ = [("dwMousePosition", COORD), ("dwButtonState", wintypes.DWORD),
                        ("dwControlKeyState", wintypes.DWORD), ("dwEventFlags", wintypes.DWORD)]

        class WINDOW_BUFFER_SIZE_RECORD(ctypes.Structure):
            _fields_ = [("dwSize", COORD)]

        class _EVENT_UNION(ctypes.Union):
            _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("MouseEvent", MOUSE_EVENT_RECORD),
                        ("WindowBufferSizeEvent", WINDOW_BUFFER_SIZE_RECORD),
                        ("pad", ctypes.c_byte * 16)]

        class INPUT_RECORD(ctypes.Structure):
            _fields_ = [("EventType", ctypes.c_ushort), ("Event", _EVENT_UNION)]

        count = wintypes.DWORD()
        if not self._k32.GetNumberOfConsoleInputEvents(self._hin, ctypes.byref(count)):
            return []
        n = count.value
        if n == 0:
            return []
        buf = (INPUT_RECORD * n)()
        read = wintypes.DWORD()
        if not self._k32.ReadConsoleInputW(self._hin, buf, n, ctypes.byref(read)):
            return []
        events: list[Event] = []
        for i in range(read.value):
            rec = buf[i]
            if rec.EventType == 0x0001:  # KEY_EVENT
                ke = rec.Event.KeyEvent
                ev = decode_key_record(ke.wVirtualKeyCode, ke.UnicodeChar or "",
                                       ke.dwControlKeyState, bool(ke.bKeyDown))
                if ev is not None:
                    events.append(ev)
            elif rec.EventType == 0x0002:  # MOUSE_EVENT
                me = rec.Event.MouseEvent
                ev = _decode_mouse_record(me.dwMousePosition.X, me.dwMousePosition.Y,
                                          me.dwButtonState, me.dwControlKeyState, me.dwEventFlags)
                if ev is not None:
                    events.append(ev)
            elif rec.EventType == 0x0004:  # WINDOW_BUFFER_SIZE_EVENT
                w, h = self.size()
                events.append(resize_event(w, h))
        return events

    def write(self, text: str) -> None:
        import ctypes
        from ctypes import wintypes

        # WriteConsoleW counts UTF-16 code units, not Python code points; pass
        # the unit count or non-BMP glyphs truncate the write (see utf16_units).
        written = wintypes.DWORD()
        write_console_w(self._k32, self._hout, text, ctypes.byref(written))

    def wake(self) -> None:
        self._k32.SetEvent(self._wake_event)

    def set_clipboard(self, text: str) -> None:
        # OSC 52 works in Windows Terminal; a GlobalAlloc path is left for later.
        import base64

        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self.write(f"\x1b]52;c;{b64}\x07")
