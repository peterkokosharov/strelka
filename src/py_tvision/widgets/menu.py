# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Menu bar, pull-down menu box, status line and info line."""

from __future__ import annotations

from ..events import Event, EventKind, Mod, key_spec
from ..geometry import Rect
from ..screen import DrawContext
from ..text import BOX_SINGLE, cut_to_width, parse_hotkey, str_width
from ..views import Option, State, View


class MenuItem:
    def __init__(self, text: str, command: int = 0, enabled: bool = True):
        self.display, self.hotkey, self.hot_index = parse_hotkey(text)
        self.command = command
        self.enabled = enabled
        self.is_separator = text == "-"


class SubMenu:
    def __init__(self, title: str, items: list[MenuItem]):
        self.display, self.hotkey, self.hot_index = parse_hotkey(title)
        self.items = items


class MenuBox(View):
    """A pull-down list of items, drawn as a framed popup."""

    def __init__(self, submenu: SubMenu, x: int, y: int):
        width = max((str_width(it.display) for it in submenu.items), default=4) + 4
        height = len(submenu.items) + 2
        super().__init__(Rect(x, y, x + width, y + height))
        self.submenu = submenu
        self.focused = self._first_enabled()

    def _first_enabled(self) -> int:
        for i, it in enumerate(self.submenu.items):
            if it.enabled and not it.is_separator:
                return i
        return 0

    def move(self, delta: int) -> None:
        n = len(self.submenu.items)
        i = self.focused
        for _ in range(n):
            i = (i + delta) % n
            it = self.submenu.items[i]
            if it.enabled and not it.is_separator:
                self.focused = i
                return

    def current_item(self) -> MenuItem | None:
        if 0 <= self.focused < len(self.submenu.items):
            return self.submenu.items[self.focused]
        return None

    def draw(self, ctx: DrawContext) -> None:
        body = self.get_style("menubox")
        sel = self.get_style("menubox.selected")
        hot = self.get_style("menu.hotkey")
        disabled = self.get_style("menu.disabled")
        frame = self.get_style("window.frame")
        box = BOX_SINGLE
        w, h = self.bounds.width, self.bounds.height
        ctx.fill(Rect(1, 1, w - 1, h - 1), " ", body)
        ctx.put(0, 0, box["tl"], frame)
        ctx.put(w - 1, 0, box["tr"], frame)
        ctx.put(0, h - 1, box["bl"], frame)
        ctx.put(w - 1, h - 1, box["br"], frame)
        ctx.hline(1, 0, w - 2, box["h"], frame)
        ctx.hline(1, h - 1, w - 2, box["h"], frame)
        ctx.vline(0, 1, h - 2, box["v"], frame)
        ctx.vline(w - 1, 1, h - 2, box["v"], frame)
        for i, item in enumerate(self.submenu.items):
            row = 1 + i
            if item.is_separator:
                ctx.hline(1, row, w - 2, box["h"], frame)
                continue
            style = sel if i == self.focused else (body if item.enabled else disabled)
            ctx.fill(Rect(1, row, w - 1, row + 1), " ", style)
            ctx.write_text(2, row, item.display, style)
            if item.hotkey is not None and item.enabled and i != self.focused:
                if 0 <= item.hot_index < len(item.display):
                    ctx.put(2 + item.hot_index, row, item.display[item.hot_index], hot)


class MenuBar(View):
    def __init__(self, bounds: Rect, submenus: list[SubMenu]):
        super().__init__(bounds)
        self.submenus = submenus
        self.options |= Option.PRE_PROCESS
        self.active = False
        self.open_index = -1
        self.box: MenuBox | None = None

    # -- geometry of the titles --------------------------------------------

    def _title_positions(self) -> list[tuple[int, int, SubMenu]]:
        out: list[tuple[int, int, SubMenu]] = []
        x = 1
        for sm in self.submenus:
            tw = str_width(sm.display) + 2
            out.append((x, tw, sm))
            x += tw + 1
        return out

    def draw(self, ctx: DrawContext) -> None:
        base = self.get_style("menu")
        sel = self.get_style("menu.selected")
        hot = self.get_style("menu.hotkey")
        ctx.fill(Rect(0, 0, self.bounds.width, 1), " ", base)
        for i, (x, tw, sm) in enumerate(self._title_positions()):
            style = sel if (self.active and i == self.open_index) else base
            ctx.fill(Rect(x, 0, x + tw, 1), " ", style)
            ctx.write_text(x + 1, 0, sm.display, style)
            if sm.hotkey is not None and not (self.active and i == self.open_index):
                if 0 <= sm.hot_index < len(sm.display):
                    ctx.put(x + 1 + sm.hot_index, 0, sm.display[sm.hot_index], hot)

    # -- open / close -------------------------------------------------------

    def open(self, index: int) -> None:
        if not self.submenus:
            return
        index %= len(self.submenus)
        positions = self._title_positions()
        x, _, sm = positions[index]
        self.active = True
        self.open_index = index
        self.box = MenuBox(sm, x, 1)
        self.box.owner = self.owner  # for theme lookup through the program
        self._set_popup(self.box)
        self.draw_view()

    def close(self) -> None:
        self.active = False
        self.open_index = -1
        self.box = None
        self._set_popup(None)
        self.draw_view()

    def _set_popup(self, box: MenuBox | None) -> None:
        prog = self.program()
        if prog is not None and hasattr(prog, "menu_popup"):
            prog.menu_popup = box

    # -- events -------------------------------------------------------------

    def handle_event(self, ev: Event) -> None:
        if self.active:
            self._handle_active(ev)
            return
        if ev.kind == EventKind.KEY:
            if ev.key == "F10" and ev.mods == Mod.NONE:
                self.open(0)
                ev.clear()
                return
            if ev.mods & Mod.ALT:
                for i, sm in enumerate(self.submenus):
                    if sm.hotkey is not None and ev.key == sm.hotkey:
                        self.open(i)
                        ev.clear()
                        return
        elif ev.kind == EventKind.MOUSE_DOWN and ev.mouse.y == self.abs_origin().y:
            ox = self.abs_origin().x
            for i, (x, tw, _sm) in enumerate(self._title_positions()):
                if ox + x <= ev.mouse.x < ox + x + tw:
                    self.open(i)
                    ev.clear()
                    return

    def _handle_active(self, ev: Event) -> None:
        box = self.box
        if box is None:
            self.close()
            return
        if ev.kind == EventKind.KEY:
            key = ev.key
            if key == "Esc":
                self.close()
            elif key == "Down":
                box.move(1)
                box.draw_view()
            elif key == "Up":
                box.move(-1)
                box.draw_view()
            elif key == "Left":
                self.open(self.open_index - 1)
            elif key == "Right":
                self.open(self.open_index + 1)
            elif key == "Enter":
                self._choose(box.current_item())
            else:
                # Item hotkey?
                for item in box.submenu.items:
                    if item.enabled and item.hotkey is not None and key == item.hotkey:
                        self._choose(item)
                        break
            ev.clear()
        elif ev.kind == EventKind.MOUSE_DOWN:
            ab = box.abs_bounds()
            if ab.contains(ev.mouse):
                row = ev.mouse.y - box.abs_origin().y - 1
                if 0 <= row < len(box.submenu.items):
                    box.focused = row
                    self._choose(box.submenu.items[row])
            else:
                self.close()
            ev.clear()

    def _choose(self, item: MenuItem | None) -> None:
        if item is not None and item.enabled and not item.is_separator and item.command:
            cmd = item.command
            self.close()
            self.emit_command(cmd)
        else:
            self.close()


class StatusItem:
    def __init__(self, label: str, key: str, command: int):
        self.label = label
        self.key_name, self.key_mods = key_spec(key) if key else ("", Mod.NONE)
        self.command = command


class StatusLine(View):
    def __init__(self, bounds: Rect, items: list[StatusItem]):
        super().__init__(bounds)
        self.items = items
        self.options |= Option.POST_PROCESS  # F-keys after the focus chain

    def _layout(self) -> list[tuple[int, int, StatusItem]]:
        out: list[tuple[int, int, StatusItem]] = []
        x = 0
        for it in self.items:
            w = str_width(it.label) + 2
            out.append((x, w, it))
            x += w
        return out

    def draw(self, ctx: DrawContext) -> None:
        base = self.get_style("status")
        hot = self.get_style("status.hotkey")
        ctx.fill(Rect(0, 0, self.bounds.width, 1), " ", base)
        for x, w, it in self._layout():
            disp, hotkey, hidx = parse_hotkey(it.label)
            ctx.write_text(x + 1, 0, cut_to_width(disp, self.bounds.width - x - 1), base)
            if hotkey is not None and 0 <= hidx < len(disp):
                ctx.put(x + 1 + hidx, 0, disp[hidx], hot)

    def handle_event(self, ev: Event) -> None:
        if ev.kind == EventKind.KEY:
            for it in self.items:
                if it.key_name and ev.key == it.key_name and ev.mods == it.key_mods:
                    self.emit_command(it.command)
                    ev.clear()
                    return
        elif ev.kind == EventKind.MOUSE_DOWN and ev.mouse.y == self.abs_origin().y:
            ox = self.abs_origin().x
            for x, w, it in self._layout():
                if ox + x <= ev.mouse.x < ox + x + w:
                    self.emit_command(it.command)
                    ev.clear()
                    return


class InfoLine(View):
    """A one-line information bar (a menu bar with no menu)."""

    def __init__(self, bounds: Rect, text: str = "", role: str = "menu"):
        super().__init__(bounds)
        self.text = text
        self.role = role

    def set_text(self, text: str) -> None:
        self.text = text
        self.draw_view()

    def draw(self, ctx: DrawContext) -> None:
        style = self.get_style(self.role)
        ctx.fill(Rect(0, 0, self.bounds.width, 1), " ", style)
        ctx.write_text(1, 0, cut_to_width(self.text, self.bounds.width - 1), style)
