# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Decode a VT/xterm input byte stream into events.

Handles CSI and SS3 function/arrow keys with xterm modifier parameters,
``ESC`` + key as Alt, SGR mouse reports (``ESC[<b;x;yM``/``m``), and
bracketed paste (``ESC[200~`` ... ``ESC[201~``). It is a pure incremental
decoder: ``feed(bytes)`` returns the events it can complete and keeps any
partial tail for the next call; ``flush()`` resolves a dangling lone ESC into
an ``Esc`` key once the caller has decided the timeout passed.
"""

from __future__ import annotations

import codecs

from ..events import (
    EventKind,
    Event,
    MB_LEFT,
    MB_MIDDLE,
    MB_RIGHT,
    Mod,
    key_event,
    mouse_event,
    paste_event,
)

ESC = 0x1B

# Final CSI letters / SS3 letters -> key name.
_CSI_LETTER = {
    "A": "Up", "B": "Down", "C": "Right", "D": "Left",
    "H": "Home", "F": "End",
    "P": "F1", "Q": "F2", "R": "F3", "S": "F4",
    "Z": "Tab",  # Shift-Tab arrives as CSI Z
}
# CSI <n> ~ keys.
_CSI_TILDE = {
    1: "Home", 2: "Insert", 3: "Delete", 4: "End", 5: "PageUp", 6: "PageDown",
    7: "Home", 8: "End",
    11: "F1", 12: "F2", 13: "F3", 14: "F4", 15: "F5",
    17: "F6", 18: "F7", 19: "F8", 20: "F9", 21: "F10", 23: "F11", 24: "F12",
}


def _mods_from_param(param: int) -> Mod:
    """xterm modifier parameter (2..8) -> Mod flags."""
    bits = param - 1
    mods = Mod.NONE
    if bits & 1:
        mods |= Mod.SHIFT
    if bits & 2:
        mods |= Mod.ALT
    if bits & 4:
        mods |= Mod.CTRL
    return mods


_CTRL_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x0A: "Enter",
    0x7F: "Backspace",
}


class VTInputDecoder:
    def __init__(self) -> None:
        self._buf = bytearray()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._in_paste = False
        self._paste: list[str] = []

    def feed(self, data: bytes) -> list[Event]:
        self._buf.extend(data)
        events: list[Event] = []
        while self._buf:
            consumed, evs = self._step()
            if consumed == 0:
                break  # need more bytes
            del self._buf[:consumed]
            events.extend(evs)
        return events

    def pending_escape(self) -> bool:
        """True while an incomplete ``ESC``-prefixed sequence is buffered.

        The caller uses this to bound its next read with the short escape
        timeout, so a lone ``ESC`` (or a truncated ``ESC [`` / ``ESC O``) is
        resolved quickly instead of waiting for the next, unrelated keystroke.
        A pending bracketed paste is not an escape in this sense.
        """
        return (not self._in_paste) and bool(self._buf) and self._buf[0] == ESC

    def flush(self) -> list[Event]:
        """Resolve a stuck ``ESC``-prefixed partial sequence into an Esc key.

        Called only after the caller's bounded escape timeout elapsed with no
        further bytes: any ``ESC`` still buffered is then a real lone Escape (or
        a sequence the terminal truncated, e.g. ``ESC [`` with nothing after).
        A single Esc key is emitted and the partial bytes are dropped so the
        parser can never wedge on them.
        """
        if self._in_paste:
            return []
        if self._buf and self._buf[0] == ESC:
            self._buf.clear()
            return [key_event("Esc")]
        return []

    # -- internal ----------------------------------------------------------

    def _step(self) -> tuple[int, list[Event]]:
        b = self._buf
        first = b[0]

        if self._in_paste:
            return self._step_paste()

        if first == ESC:
            if len(b) == 1:
                return 0, []  # wait: might be a sequence or a lone Esc
            second = b[1]
            if second == ord("["):
                return self._step_csi()
            if second == ord("O"):
                return self._step_ss3()
            if second == ESC:
                # ESC ESC -> one Esc, keep the rest.
                return 1, [key_event("Esc")]
            # ESC + char == Alt+char
            text, length = self._decode_one(1)
            if text is None:
                return 0, []
            name = text.upper() if text.isalpha() else text
            return 1 + length, [key_event(name, Mod.ALT, text=text)]

        if first < 0x20 or first == 0x7F:
            name = _CTRL_NAMES.get(first)
            if name is not None:
                return 1, [key_event(name)]
            # Ctrl+letter: 0x01->A .. 0x1A->Z
            if 1 <= first <= 26:
                return 1, [key_event(chr(ord("A") + first - 1), Mod.CTRL)]
            return 1, []  # drop other controls

        # Printable: decode one UTF-8 character.
        text, length = self._decode_one(0)
        if text is None:
            return 0, []
        name = text.upper() if (len(text) == 1 and text.isalpha()) else text
        return length, [key_event(name, text=text)]

    def _decode_one(self, offset: int) -> tuple[str | None, int]:
        """Decode exactly one character starting at ``offset`` in the buffer."""
        b = self._buf
        for length in range(1, 5):
            if offset + length > len(b):
                return None, 0
            try:
                chunk = bytes(b[offset:offset + length])
                text = chunk.decode("utf-8")
                return text, length
            except UnicodeDecodeError:
                continue
        # Invalid byte: consume one, emit replacement.
        return "�", 1

    def _step_csi(self) -> tuple[int, list[Event]]:
        b = self._buf
        # b[0]=ESC b[1]='['
        i = 2
        if i < len(b) and b[i] == ord("<"):
            return self._step_mouse_sgr()
        params_start = i
        while i < len(b) and (0x30 <= b[i] <= 0x3F):  # parameter / intermediate bytes
            i += 1
        if i >= len(b):
            return 0, []  # incomplete
        final = b[i]
        param_str = bytes(b[params_start:i]).decode("ascii", "replace")
        consumed = i + 1

        # Bracketed paste start.
        if param_str == "200" and final == ord("~"):
            self._in_paste = True
            self._paste = []
            return consumed, []

        params = [int(p) for p in param_str.split(";") if p.isdigit()] if param_str else []
        mods = Mod.NONE
        if len(params) >= 2:
            mods = _mods_from_param(params[1])

        if final == ord("~"):
            code = params[0] if params else 0
            name = _CSI_TILDE.get(code)
            if name:
                return consumed, [key_event(name, mods)]
            return consumed, []

        letter = chr(final)
        name = _CSI_LETTER.get(letter)
        if name:
            if name == "Tab":
                return consumed, [key_event("Tab", mods | Mod.SHIFT)]
            return consumed, [key_event(name, mods)]
        return consumed, []

    def _step_ss3(self) -> tuple[int, list[Event]]:
        b = self._buf
        # ESC O <letter>
        if len(b) < 3:
            return 0, []
        letter = chr(b[2])
        name = _CSI_LETTER.get(letter)
        if name:
            return 3, [key_event(name)]
        return 3, []

    def _step_mouse_sgr(self) -> tuple[int, list[Event]]:
        b = self._buf
        # ESC [ < params (M|m)
        i = 3
        while i < len(b) and b[i] not in (ord("M"), ord("m")):
            i += 1
        if i >= len(b):
            return 0, []
        final = b[i]
        body = bytes(b[3:i]).decode("ascii", "replace")
        consumed = i + 1
        try:
            code, sx, sy = (int(p) for p in body.split(";"))
        except ValueError:
            return consumed, []
        x = sx - 1
        y = sy - 1
        mods = Mod.NONE
        if code & 4:
            mods |= Mod.SHIFT
        if code & 8:
            mods |= Mod.ALT
        if code & 16:
            mods |= Mod.CTRL
        if code & 64:  # wheel
            wheel = 1 if (code & 1) == 0 else -1
            return consumed, [mouse_event(EventKind.MOUSE_WHEEL, x, y, wheel=wheel, mods=mods)]
        button_bits = code & 3
        buttons = {0: MB_LEFT, 1: MB_MIDDLE, 2: MB_RIGHT}.get(button_bits, 0)
        if code & 32:  # motion
            return consumed, [mouse_event(EventKind.MOUSE_MOVE, x, y, buttons=buttons, mods=mods)]
        if final == ord("M"):
            return consumed, [mouse_event(EventKind.MOUSE_DOWN, x, y, buttons=buttons, mods=mods)]
        return consumed, [mouse_event(EventKind.MOUSE_UP, x, y, buttons=buttons, mods=mods)]

    def _step_paste(self) -> tuple[int, list[Event]]:
        b = self._buf
        end = bytes(b).find(b"\x1b[201~")
        if end == -1:
            # No terminator yet: keep accumulating but do not consume raw bytes
            # until we can decode text safely; wait for more.
            return 0, []
        text = self._decoder.decode(bytes(b[:end]))
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._in_paste = False
        return end + len(b"\x1b[201~"), [paste_event(text)]
