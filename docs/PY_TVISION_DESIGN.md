# py_tvision - design

Status: design draft, 2026-11-25. Nothing here is built yet.

## 1. Goal and non-goals

**Goal.** A small Python text-UI library in the spirit of Turbo Vision (views in a tree, windows with
box frames, menu bar, status line, modal dialogs, mouse, colour themes) that is good enough to carry
a full Python port of Layka ("Strelka") with the same look and behaviour as the C++ version.

Hard rules:
- Production code: Python standard library only (Python >= 3.12). No `curses` (CPython for Windows
  ships without `_curses`), no `textual`, `rich`, `pydantic`, `psutil`.
- Runs on Windows 10 1809+/11 (Windows Terminal, conhost), Linux, macOS.
- Independent design (see section 12). Not a translation of Borland-origin tvision code.

Non-goals (first version):
- Legacy consoles without VT output (pre-Windows 10 1809). We refuse with a clear message.
- Full tvision API: no streams/resources (`TStreamable`), no `TEditor`/`TMemo` with undo and
  search, no file-open dialog, no outline view, no colour selector, no help system, no validators.
- Overlapping-window desktop management beyond what is needed (tile/cascade, window list).
- curses-style terminfo database: we use a fixed modern VT/xterm subset.
- Linux console (`/dev/tty1`) GPM mouse, far2l protocol, kitty keyboard protocol (later, maybe).

## 2. What Layka actually uses from tvision (inventory)

Counted by grep over `src/main.cpp` (2542 lines), `src/core.h`, `src/proc.*` on 2026-11-25.
`core.h` (1858 lines) is pure logic (wrap, markdown, prompt editing, width, i18n) with no tvision
include; it ports to plain Python. The tvision-facing code is about lines 1200-2542 of `main.cpp`.

**tvision types referenced: ~33.** By references: `TRect` 50, `TColorAttr` 21, `TButton` 13,
`TDialog` 12, `TInputLine` 11, `TColor` 10, `TProgram` 8, `TPalette` 8, `TScrollBar` 7,
`TScreen` 6, `TEvent` 6, `TColorRGB` 6, `TStatusItem` 5, `TStaticText` 5, `TLabel` 5, `TView` 4,
`TStringCollection` 4, `TMenuBar` 4, `TDrawBuffer` 4, `TStatusLine` 3, `TSortedListBox` 3,
`TPoint` 3, `TColorBIOS` 3, `TChDirDialog` 3, `TApplication` 3, `TParamText` 2, `TListBox` 2,
`TStatusDef`, `TClipboard`, `TStringView`, `TSpan`, `TProgInit`, `TWindowInit` 1-2 each; plus
the `messageBox()` function and `deskTop`.

**Layka's own subclasses: 8.** `TLaykaApp` (TApplication: `idle`, `getPalette`),
`TLaykaDialog` (full-screen TDialog: `handleEvent`, `calcBounds`, `changeBounds`),
`TPermDialog` (TDialog: `handleEvent`), `TMsgListBox` (TListBox: own `draw` with per-line colour
classes and inline code spans), `TPromptBox` (TView: 3-row soft-wrapped multi-line input with
history, mouse click, paste), `TInfoBar` (a TMenuBar with no menu: one info line),
`TStatusParam` (TParamText with a "hot" colour), `TChronoStringCollection` (unsorted list data).
Overrides: `draw` 4, `handleEvent` 4, `getPalette` 2, `setState` 1, `calcBounds`/`changeBounds` 1.

**Commands: 18.** Own: `cmSend, cmStop, cmResetCtx, cmPickModel, cmPickFolder, cmModelsReady,
cmOpenImage, cmCopyAnswer, cmKeysHelp, cmPermOnce, cmPermAlways, cmPermDeny` (12). Standard:
`cmOK, cmCancel, cmQuit, cmYes, cmMenu` (+ the implicit `cmScreenChanged` on resize).

**Events:** `evKeyDown`, `evCommand`, `evMouseDown`, plus `putEvent` from `idle()` (models fetch
done) and paste as one burst (`kbPaste` + `textEvent`). **Key codes: 37** distinct (`kbAlt*` 15,
arrows/Home/End/PgUp/PgDn, `kbCtrlHome/End`, `kbEsc`, `kbF1`, `kbF10`, `kbBack`, `kbDel`,
`kbAltEnter`, `kbCtrlEnter`, `kbCtrlJ`). Alt-letter keys must work under non-Latin layouts
(Windows: by virtual key).

**Flags/features:** `growMode` 13 uses (`gfGrowLoX/HiX/LoY/HiY`: the layout is built at 80x25 and
stretched on resize), `sfSelected/sfFocused/sfActive/sfCursorVis`, `ofSelectable|ofFirstClick`,
`wfMove` cleared, `bfDefault/bfNormal`, `mfConfirmation|mfYesButton|mfNoButton`.
Drawing API: `getColor` 13, `drawView` 13, `moveStr` 9, `moveChar` 6, `writeLine` 4,
`setCursor` 3. Modal: `execView` 5 (nested: a permission dialog opens from `idle()` while another
modal loop runs), `endModal` 4. Colour: direct RGB (`0x0000AF`, `0x003A3A`), BIOS 16-colour
fallback, bold, `TScreen::screenMode` test for 256/true colour. Clipboard: `TClipboard::setText`
(system clipboard, OSC 52 fallback). Unicode: UTF-8 everywhere, wide CJK (there is a `zh` UI
language), `~X~` hotkey markers in labels/buttons from `lang/*.ini`.

**Not used:** pull-down menus (the menu bar is only an info line; F10 does nothing), `TEditor`,
`TMemo`, `TFileDialog`, check boxes, radio buttons, history lists, validators, window move/resize
by mouse, multiple windows on the desktop, streams.

So the Layka subset is: application + desktop + one full-screen dialog + modal dialogs, button,
label, static/param text, single-line input, list box (sorted, type-ahead), scroll bar, status line,
info line, message box, folder picker, a custom multi-line input view, clipboard, mouse clicks,
resize, threads posting to the UI. The phase-1 demo adds a real pull-down menu because a
Turbo-Vision-like library without one is a toy.

## 3. Architecture taken from tvision (behaviour, not code)

- **View tree.** Every visible thing is a view with bounds relative to its owner. A group owns child
  views in z-order and draws them back to front with clipping; window and dialog are groups with
  a frame; the application is a group of menu bar, desktop and status line.
- **Event routing in three phases.** Mouse events go to the topmost view under the pointer.
  Key and command events go to the focused chain (the "current" child at each level, down to the
  leaf), but views flagged pre-process see them before the focused chain and post-process views
  after it (this is how buttons react to Alt-hotkeys and the status line to F-keys). An unhandled
  event bubbles back up; the application turns unhandled keys of status items into commands.
- **Commands.** Integers posted as events; views can enable/disable commands globally (disabled
  buttons and menu items grey out).
- **Modal loop.** `exec_view(dialog)` inserts the view, runs a nested event loop until
  `end_modal(cmd)`, removes it and returns `cmd`. Nesting is allowed (Layka relies on it).
- **Idle.** When no event is pending the loop calls `idle()` (Layka drains its message queue,
  ticks a spinner at 10 Hz, opens queued permission dialogs).
- **Resize.** The platform reports a new size; the application resizes itself and every child is
  recomputed from its grow mode; then a full redraw.
- **Palettes.** tvision maps a view's colour index through each owner's palette to an application
  palette byte. We replace this with named theme roles (section 7): simpler to read and change.
- **Screen.** Views write cells into one off-screen buffer; a flush compares with what the terminal
  shows and sends only changed runs (tvision `dispbuff.cpp`, magiblot).

## 4. Module layout

```
py_tvision/
  __init__.py            public names
  geometry.py            Point, Rect (intersect, union, move, grow, contains)
  text.py                cell width, cut/pad to width, ~X~ hotkey parsing, UTF-8 safe helpers
  color.py               RGB -> xterm-256 -> 16 conversion, colour depth detection
  theme.py               Style(fg, bg, bold, ...), role table, built-in themes
  screen.py              Cell grid, DrawBuffer, damage tracking, diff -> VT output string
  events.py              Event, key/modifier/mouse constants, command ids, thread-safe post queue
  views.py               View, Group: bounds, grow modes, state/option flags, draw, focus, routing
  window.py              Frame, Window, Dialog, shadow
  app.py                 Program/Application, Desktop, main and modal loops, idle, resize
  platform/
    __init__.py          pick backend; Terminal interface (start, stop, size, read, write, wake)
    vtinput.py           VT byte decoder: CSI/SS3 keys + modifiers, SGR mouse, bracketed paste
    win32.py             ctypes console: modes, ReadConsoleInputW decode, wait, clipboard, CPs
    posix.py             termios raw mode, select loop, SIGWINCH self-pipe, OSC 52 clipboard
    headless.py          in-memory terminal for tests and snapshots
  widgets/
    static.py            StaticText, ParamText, Label (focus link + hotkey)
    button.py            Button (default, hotkey, shadow, click/press)
    inputline.py         InputLine (scroll, selection, clipboard, max length, Unicode)
    scrollbar.py         ScrollBar (arrows, page, thumb drag)
    listview.py          ListViewer, ListBox, SortedListBox (type-ahead)
    textbox.py           multi-line soft-wrap input (generic form of Layka's TPromptBox)
    menu.py              MenuBar, MenuBox (pull-down), StatusLine (+ InfoLine)
    msgbox.py            message_box(), input_box()
    folderdlg.py         FolderDialog (dir list + path input; replaces TChDirDialog)
  demo/                  phase-1 demo, key/mouse echo, colour chart
```

## 5. Platform layer (stdlib mechanisms per OS)

Common interface: `start()` (enter raw mode, alternate screen, mouse on, hide cursor),
`stop()` (restore exactly what was saved), `size()`, `read(timeout) -> list[Event]`,
`write(str)`, `wake()` (callable from any thread), `set_clipboard(text)`.

**Windows (`platform/win32.py`, `ctypes` + `ctypes.wintypes`).**
- Handles: `GetStdHandle(STD_INPUT_HANDLE / STD_OUTPUT_HANDLE)`; refuse if not a console
  (`GetConsoleMode` fails), e.g. output redirected.
- Save input/output modes and code pages; on start: input mode `ENABLE_WINDOW_INPUT |
  ENABLE_MOUSE_INPUT | ENABLE_EXTENDED_FLAGS`, clear `ENABLE_PROCESSED_INPUT` (Ctrl-C as a key),
  `ENABLE_LINE_INPUT`, `ENABLE_ECHO_INPUT`, `ENABLE_QUICK_EDIT_MODE` (else the mouse selects
  text). Output mode `ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING`, clear
  `ENABLE_WRAP_AT_EOL_OUTPUT`; `DISABLE_NEWLINE_AUTO_RETURN`. If VT cannot be enabled: stop with a
  message (non-goal). `SetConsoleOutputCP(65001)`, `SetConsoleCP(65001)`.
- Input: `WaitForMultipleObjects([hIn, hWakeEvent], timeout)` (no busy loop; `wake()` calls
  `SetEvent` from worker threads), then `GetNumberOfConsoleInputEvents` + `ReadConsoleInputW` into
  an `INPUT_RECORD` array. Decode `KEY_EVENT` (key down only; `wVirtualKeyCode`,
  `uChar.UnicodeChar`, `dwControlKeyState`), `MOUSE_EVENT` (buttons, wheel via
  `MOUSE_WHEELED`, move), `WINDOW_BUFFER_SIZE_EVENT` -> resize (re-read the *window* size from
  `GetConsoleScreenBufferInfo.srWindow`, not the buffer size).
- Key decoding details: Alt+letter by virtual key, so it works under Cyrillic/Greek layouts
  (Layka needs this); AltGr arrives as `RIGHT_ALT|LEFT_CTRL` and must yield the character, not
  Alt; UTF-16 surrogate pairs arrive as two records; Alt+numpad and dead keys give text on the
  key-up record only.
- Paste: `ReadConsoleInputW` has no bracketed paste. Heuristic: printable key records already
  waiting in one batch (more than a few, typed faster than a human) are merged into one paste event;
  a newline inside it stays text (Layka's rule). Windows Terminal also offers VT input
  (`ENABLE_VIRTUAL_TERMINAL_INPUT`) with real bracketed paste; kept as a later option that reuses
  `vtinput.py`.
- Output: one `WriteConsoleW` (or `os.write` of UTF-8 bytes) per frame; alternate screen with
  `ESC[?1049h` (supported by Windows 10 1809+ conhost and Windows Terminal).
- Clipboard: `OpenClipboard`, `EmptyClipboard`, `GlobalAlloc/GlobalLock`, `SetClipboardData
  (CF_UNICODETEXT)`; read the same way for paste-from-menu.
- Restore: `try/finally` + `atexit` + `SetConsoleCtrlHandler` for close/logoff.

**POSIX (`platform/posix.py`).** `termios` + `tty.setraw`-like flags on `/dev/tty` (or stdin if a
tty); save attributes and restore on exit. `select.select([tty_fd, wake_pipe_r], [], [], timeout)`;
`os.pipe()` self-pipe written by `wake()` and by the `SIGWINCH` handler (`signal.signal`), size
from `os.get_terminal_size`. Start sequence: alternate screen `?1049h`, hide cursor, mouse
`?1000h ?1002h ?1006h` (SGR), bracketed paste `?2004h`, `?1036h` (meta sends ESC); stop reverses.
Bytes go through `codecs.getincrementaldecoder('utf-8')(errors='replace')` and `vtinput.py`.
ESC ambiguity: a lone ESC is a key only after ~40 ms with no follow-up byte. Clipboard: OSC 52
(`ESC]52;c;<base64>BEL`) by default; optional `pbcopy` / `wl-copy` / `xclip` through `subprocess`
when present (checked with `shutil.which`). `SIGTSTP`/`SIGCONT`: restore and re-enter.

**`vtinput.py`** decodes CSI and SS3 sequences (`ESC[A`, `ESC[1;5H`, `ESC[3~`, `ESCOP`...), the
xterm modifier parameter (2=Shift .. 8=Ctrl+Alt+Shift), `ESC` + key as Alt, SGR mouse
`ESC[<b;x;yM/m` (buttons, wheel 64/65, drag 32 bit), bracketed paste `ESC[200~ ... ESC[201~`, and
`ESC[?u`-free plain modes only. Table-driven, ~60 entries.

**Width (`text.py`).** `unicodedata.east_asian_width(ch) in ('W','F')` -> 2; combining marks
(`unicodedata.combining`, categories `Mn`, `Me`) and zero-width (`Cf`, ZWJ, variation selectors)
-> 0; controls -> replaced. Emoji with VS16 count as 2. A cell holds a grapheme (base +
combining), so a combining mark never takes a column. Layka's `core.h` `cpWidth` table (Markus
Kuhn style) is used as cross-check in tests. Where terminals disagree (conhost and some emoji),
a wide character at the last column is replaced by a space, and the next frame redraws the whole
row whenever it contains a wide character (cheap insurance against drift).

## 6. Event model

`Event(kind, key, mods, text, mouse_pos, buttons, command, info)` with kinds `KEY`, `MOUSE_DOWN`,
`MOUSE_UP`, `MOUSE_MOVE`, `MOUSE_WHEEL`, `COMMAND`, `BROADCAST`, `PASTE`, `RESIZE`. Keys are
`Key` names plus modifier bits (`ALT`, `CTRL`, `SHIFT`), not packed scan codes; `key_code("Alt+Q")`
helps tables. Commands are ints in an `IntEnum` for the standard set, apps add their own above
1000. `Event.clear()` marks it handled.

One UI thread owns all views. Worker threads (rex reader, model fetch, helpers) only call
`app.post(fn_or_event)`: a `queue.SimpleQueue` plus `terminal.wake()`. The loop is:

```
while running:
    events = terminal.read(timeout=next_timer_or_idle)
    for ev in events + posted: route(ev)
    if nothing happened: idle(); timers
    if screen.dirty: flush (at most ~60 frames/s)
```

`exec_view()` runs the same loop nested until `end_modal()`; `idle()` is called in nested loops too.
Timers (`app.every(0.1, fn)`) replace hand-written clock checks in `idle()`.

## 7. Rendering, colour and theme

**Buffer.** The screen is a list of rows; each row is two parallel lists `chars` (str per cell,
`""` for the right half of a wide char) and `attrs` (small int index into an interned `Style`
table). Views draw through a `DrawContext` clipped to their visible rectangle; groups clip children.
Full redraw of the view tree into the back buffer is the default; damaged-row tracking avoids work
for rows nobody touched. `draw_view()` from a widget only marks it dirty; drawing happens once per
loop turn (coalesces a token stream of hundreds of updates per second into one frame).

**Flush/diff.** Per row: if `back.chars == front.chars and back.attrs == front.attrs` (C-speed list
compare) skip; else find changed runs, emit cursor move `ESC[y;xH`, SGR only when the style changes,
the text; build one string per frame and write it once, wrapped in synchronized output
`ESC[?2026h ... ESC[?2026l` (ignored where unsupported; avoids tearing in Windows Terminal).
Cursor: shown at the focused view's cursor position, `ESC[?25h/l`, shape via `ESC[n q`.

**Colour depth.** Detect: `COLORTERM=truecolor|24bit`, `WT_SESSION` (Windows Terminal), Windows
console with VT -> 24-bit; `TERM` contains `256color` -> 256; otherwise 16. Override with an env
variable / ini key (`colors = 16|256|24bit`). `color.py` maps RGB to the nearest xterm-256 entry
(6x6x6 cube + grey ramp, by squared distance in a perceptual-ish weighting) and to 16 colours by
hue/lightness buckets. Our own code; magiblot's `colors.cpp` HCL approach (MIT) may be ported if
the simple mapping looks wrong.

**Themes.** A theme is a dict `role -> Style`. Roles are names, e.g. `desktop`, `window.frame`,
`window.frame.active`, `window.title`, `dialog.body`, `button`, `button.default`,
`button.focused`, `button.hotkey`, `button.shadow`, `input`, `input.selected`, `input.arrows`,
`list`, `list.focused`, `list.selected`, `scrollbar`, `menu`, `menu.selected`, `menu.hotkey`,
`menu.disabled`, `status`, `status.hotkey`, `label`, `label.hotkey`, `shadow`. Widgets ask for a
role; a view may override roles locally (Layka's message list classes `msg.you`, `msg.rex`,
`msg.code`, `msg.diff.add` ... become roles too).
Built-in themes:
- `classic` - the Turbo Vision look: grey dialogs, cyan/blue desktop, green buttons, black shadows.
  Colours chosen by us, not copied from Borland's palette byte strings.
- `modern` - same layout and box drawing, dark slate background, one accent colour, softer greys;
  Layka's high-contrast input fields (white on `#0000AF`) as in the C++ version.
- `mono` - for 16-colour or no-colour terminals (`NO_COLOR` respected).
"Fason" details that matter: double-line frame for the active window, single for inactive; title
centred with spaces; buttons with the half-block shadow (`▄`/`▀`) and a press animation; window
shadow drawn by darkening the cells under it (not black blocks); `▲▼◆` arrows and `░▒` scroll
track; ASCII fallback set (`+-|#`) when the output is not UTF-8.

## 8. Widget set (minimal, matching Layka + demo)

| Widget | Needed by | Notes |
|---|---|---|
| Application, Desktop | all | info line on top, status line at bottom |
| Window, Dialog, Frame | main view, all dialogs | close box, no move needed for Layka; drag in phase 3 |
| Button | 13 refs | default button takes Enter; `~X~` hotkey; disabled state |
| Label, StaticText, ParamText | labels, help text, status | Label focuses its linked view |
| InputLine | endpoint, model, workspace | horizontal scroll, selection, Ctrl-C/V/X, max chars |
| ScrollBar | lists | linked to list views |
| ListBox, SortedListBox | messages, models, permission detail | custom per-item draw hook, type-ahead |
| TextBox (multi-line) | prompt | generic version of TPromptBox; logic from core.h PromptEdit |
| StatusLine, InfoLine | bottom/top lines | key -> command table, hints |
| MenuBar, MenuBox | demo (Layka may adopt later) | Alt-letter, F10, mouse, submenus one level |
| message_box | quit confirm | Yes/No/OK/Cancel |
| FolderDialog | workspace picker | our own simple design: path input + dir list + drive list on Windows |
| Clipboard | Alt-C | system clipboard, OSC 52 fallback |

## 9. Hard parts and risks

1. **Windows input fidelity.** Alt vs AltGr, non-Latin layouts, dead keys, surrogates, paste
   detection without bracketed paste, Ctrl-Enter/Alt-Enter (Windows Terminal grabs Alt-Enter for
   full screen unless the setting is off), mouse lost when QuickEdit is re-enabled by the user.
   Mitigation: a key/mouse echo demo from day one, recorded `INPUT_RECORD` fixtures in tests.
2. **Terminal differences.** Windows Terminal (good: true colour, mouse, sync output);
   conhost (VT works on Win10 1809+, true colour yes, some emoji widths wrong, slower);
   IntelliJ terminal (JediTerm; runs through ConPTY on Windows, mouse and Alt keys partly eaten
   by the IDE, true colour ok); VS Code terminal (xterm.js: good, but Ctrl/Alt shortcuts may be
   captured by VS Code; F1 opens its command palette). macOS Terminal.app: 256 colours only, no
   true colour -> must downgrade. Mitigation: colour depth override, keys always also reachable by
   a second binding (Layka already has Alt-Q and Alt-X), a manual test matrix per release.
3. **Wide and complex characters.** CJK labels (`zh`), emoji in model output, combining marks;
   terminal and our width table can disagree, leaving shifted rows. Mitigation in section 5; tests
   with CJK/emoji/combining strings against `core.h` widths.
4. **Performance in pure Python.** 200x60 = 12,000 cells. Budget: full tree draw + diff under
   10 ms on a laptop. Mitigation: row-level list comparison, interned styles, dirty flag with frame
   cap, no per-cell objects, list views draw only visible rows, message wrapping done once per
   entry (Layka already does this). Measure in phase 1 with a stress demo (fast token stream).
5. **Restoring the terminal on every exit path** (exception, Ctrl-Break, SIGTERM, closed window).
   A broken terminal after a crash is the worst first impression. Mitigation: one `Terminal` context
   manager, `atexit`, signal and console-ctrl handlers, a crash test in CI on POSIX with `pty`.
6. **Threading.** Only the UI thread touches views; everything else goes through `post()`.
   A violation corrupts the screen silently; a debug check asserts the thread id in `draw_view()`.
7. **Scope creep toward full tvision.** The table in section 8 is the scope; anything else needs a
   Layka use case first.

## 10. Size estimate (lines of Python, without tests)

| Module | LOC |
|---|---|
| geometry.py | 80 |
| text.py (width, cut, hotkeys) | 200 |
| color.py | 150 |
| theme.py (roles + 3 themes) | 220 |
| screen.py (buffer, draw context, diff/flush) | 400 |
| events.py | 180 |
| views.py (View, Group, routing, focus, grow modes, modal) | 800 |
| window.py (Frame, Window, Dialog, shadow) | 300 |
| app.py (Program, Desktop, loops, idle, timers, resize) | 300 |
| platform/__init__ + headless | 180 |
| platform/vtinput.py | 350 |
| platform/win32.py | 550 |
| platform/posix.py | 250 |
| widgets: static 120, button 160, inputline 320, scrollbar 180, listview 380, textbox 350 | 1,510 |
| widgets: menu (bar, box, status, info) 550, msgbox 120, folderdlg 250 | 920 |
| demo/ | 250 |
| **Total library** | **~6,600** |

Tests: about 2,500 more. For comparison: Strelka on top (its `core.h` logic ~1,500 Python lines,
UI ~1,000, process/bridge ~600) is a separate estimate of ~3,000.

## 11. Test strategy

Behaviour and integration only; no tests for getters, dataclasses or constants.
- **Headless snapshot tests.** `platform/headless.py` gives a terminal of any size; a test builds a
  view tree, feeds events, and compares the screen to a golden text file (characters) plus a
  compact style map (one letter per role). Golden files live in `tests/snapshots/`, are readable in
  a diff, and are regenerated only on purpose (`--update-snapshots`).
- **Round-trip render test.** A tiny VT interpreter (test-only) applies the flush output to an
  empty grid; the result must equal the back buffer after random sequences of draws. This guards
  the diff/flush code, the riskiest performance-driven piece.
- **Input decoder tables.** Byte sequences -> events for `vtinput.py` (keys with modifiers, SGR
  mouse, paste split across reads, lone ESC); synthetic `INPUT_RECORD` structures -> events for
  `win32.py` (decoder is a pure function and runs on every OS; only the reader needs Windows).
- **Behaviour scenarios.** Tab order and Alt-hotkeys, default button on Enter, modal dialog
  returns its command, nested modal from `idle()`, resize re-layout via grow modes (80x25 ->
  132x40 -> back), list type-ahead and scrolling, text box wrapping with CJK and emoji, paste of
  multi-line text, posted events from a worker thread.
- **Real terminal smoke (POSIX, test-only).** `pty.fork()` runs the demo, sends keys, checks that
  the terminal is restored (`stty -a` equal before/after), also after a forced exception.
- **Manual matrix per release.** Windows Terminal, conhost, IntelliJ, VS Code, a Linux terminal,
  macOS Terminal.app; checklist of 15 items (frames, colours, mouse click, wheel, Alt keys, paste,
  resize, CJK, clipboard, exit restore).
- **Performance check.** Demo stress mode prints frame times; a test fails if a full 200x60 redraw
  plus flush exceeds a generous bound.

## 12. Build order

- **Phase 0 - platform and screen.** `geometry`, `text`, `color`, `screen`, `platform/*`,
  `vtinput`; demos: key/mouse echo and colour chart on Windows Terminal, conhost, Linux.
  Done when: every key in Layka's inventory decodes right on both OSes, terminal restores on crash.
- **Phase 1 - runnable demo.** `events`, `views`, `window`, `app`, `theme` (classic + modern),
  widgets button, label, static text, input line, scroll bar, list box, menu bar + menu box,
  status line, message box. Demo: desktop with one window; menu `File` (New window, Dialog...,
  Exit) and `Help` (About); status line `F1 Help  Alt-X Exit`; a dialog with labelled input line,
  a list with scroll bar, OK/Cancel; mouse clicks; resize. Snapshot tests for each.
- **Phase 2 - Layka subset complete.** Sorted list type-ahead, param text, multi-line text box,
  info line, folder dialog, clipboard, paste, nested modal + idle + timers + `post()`, mono
  theme, ASCII fallback. A Layka screen mock-up driven by fake data matches the C++ layout.
- **Phase 3 - polish.** Window drag and resize, shadows by darkening, press animation, sync
  output, colour depth override, performance pass, manual terminal matrix.
- **Phase 4 - Strelka** on top (separate plan).

## 13. Licence

Facts from `tvision/COPYRIGHT`: Borland made the original Turbo Vision source public with a
disclaimer only, no licence grant (the rights most likely sit with Embarcadero today). magiblot's
modifications and from-scratch code are MIT (Copyright 2019-2025 magiblot).

Rules for py_tvision:
- **Borland-origin files: read for behaviour only, never translate.** All of
  `tvision/source/tvision/*.cpp` that carry "Copyright (c) 1994 by Borland International"
  (e.g. `tview.cpp`, `tgroup.cpp`, `tprogram.cpp`, `tbutton.cpp`, `tinputli.cpp`, `tlstview.cpp`,
  `tchdrdlg.cpp`, `tscreen.cpp`, `tmenu*.cpp`, `tstatusl.cpp`, `msgbox.cpp`), the `.asm` files,
  and the Borland parts of `include/tvision/*.h`, including the palette byte strings
  (`cpAppColor`, `cpAppBlackWhite`, `cpAppMonochrome`): we define our own role-based themes and
  our own colour values instead. Python names are our own (`View`, `Group`, `exec_view`,
  `Event.KEY`), not a header-by-header copy.
- **magiblot-origin (MIT) files: ideas may be ported, keep his notice.** `source/platform/*`:
  `win32con.cpp`, `conctl.cpp`, `termio.cpp`, `ansiwrit.cpp`, `dispbuff.cpp`, `colors.cpp`,
  `winwidth.cpp`, `unixclip.cpp`, `sigwinch.cpp`, `events.cpp`, and `tvision/tclipbrd.cpp`.
  If code is ported from them, the file gets a line "Parts derived from magiblot/tvision,
  Copyright 2019-2025 magiblot, MIT" and `py_tvision/LICENSES/tvision-MIT.txt` holds the full text.
- **Third-party code inside platform/:** `strings.cpp` (Milo Yip, MIT) and `ttext.cpp`
  (Bjoern Hoehrmann's UTF-8 decoder, MIT). Not needed: Python has `codecs` and `str`.
- py_tvision itself: MIT, author Peter Kokosharov <peter.kokosharov@gmail.com>, like Layka.
- **Name:** "Turbo Vision" is a Borland product name. "py_tvision" is fine as a working name;
  before a public release consider a neutral name (and say "inspired by Turbo Vision" in the README).

## 14. Conflicts found in py_port/ (noted, not fixed)

- The earlier plan builds on Textual, Rich, Pydantic and Playwright; `pyproject.toml` and
  `requirements.txt` pin them (and disagree: `rich` 13.9.4 vs 14.2.0, `pygments` 2.18.0 vs
  2.19.2). This breaks the stdlib-only rule and is replaced by this design.
- `src/strelka/config.py` imports `pydantic` and `pydantic_settings`; it must move to
  `tomllib`/`configparser` + plain dataclasses. Layka reads `layka.ini` (inih format); the Python
  port should read the same ini, not invent TOML (check `configparser` differences: inline
  comments, `%` interpolation - use `interpolation=None`).
- The earlier plan describes a JSONL protocol (`token`, `tool_call`, ... outgoing `chat` with `messages`)
  that does not match what Layka sends today (`chat` with `text`, `model`, `reset`, `stop`) - the
  C++ `RexBridge` and ai-rex are the source of truth.
- `requires-python = ">=3.11"` while the stated target is >= 3.12; plan files are in Bulgarian
  while the repository's documents are English.
- Mermaid: the earlier plan uses Playwright/kroki; Layka uses the vendored `merman` binary.

## 15. UI / logic split (owner rule, 2026-11-25)

A hard line separates the **UI layer** (the py_tvision toolkit plus the
view/widget tree) from the **logic layer** (configuration, talking to the
model / agent runtime, the JSONL bridge). Rules:

- No business logic in the application entry point. `main()` only *wires*: it
  opens a terminal, builds the config, constructs the UI and the logic
  objects, connects them (callbacks / `post()`), and runs the loop.
- Widgets never import the rex bridge or the config loader directly; they
  raise events / commands. The application object (the only place that knows
  both sides) translates commands into logic calls and posts results back to
  the UI thread with `Program.post()`.
- `py_tvision/*` has no dependency on `strelka.*`; it is a generic toolkit. The
  Strelka-specific glue lives in the Strelka app layer (phase 4), not here.
- The phase-1 demo keeps this shape: `examples/demo.py` `main()` only wires;
  all interaction lives in the `DemoApp` methods, and the demo pulls in no
  logic module. A reviewer flagged an earlier `main` that mixed the two; this
  structure is the fix.

## 16. Key capture, configurable bindings, alternative paths (owner rule, 2026-11-25)

Terminals and window managers commonly **swallow keys before the application
sees them**: on Linux/XFCE (the owner's Mint machine) **F1** opens the
terminal/WM help, and **F10**, **F11** and some **Ctrl-chords** are often
grabbed too; IDE and editor terminals grab more (see section 9.2). Therefore:

- **No critical action is bound to F1 (or any single function key) alone.**
  Every function-key action must also be reachable by a menu item *and* a
  non-function-key binding. In the demo, Help/About, Dialog and Exit each
  have a menu entry; Exit is `Alt-X`, not an F-key.
- **Key bindings are data, not hard-coded.** The `StatusLine` is already a
  configurable table of `StatusItem(label, key, command)`; `key` is parsed
  with `key_spec()` so it can come from config. A future `KeyMap` (config
  section `[keys]`) will let the user remap any binding; the toolkit must
  read bindings from that table rather than testing key names inline in
  widget code.
- **Test which keys actually arrive.** The input layer is exercised with the
  key/mouse echo demo (phase 0) on each target terminal; do not assume F1,
  F10 or F11 reach the app. The headless decoder tests cover the decoding;
  the manual matrix (section 11) must include a "which keys arrive" pass per
  terminal, explicitly checking F1/F10/F11 and the Ctrl-chords the app uses.

### 15.1 Three layers, one core many faces (owner addendum, 2026-11-25)

The split is **three** layers, and the refactor must leave a clean seam for
all three:

1. **Functional core** - config plus the agent/model runtime (librex / libkiko
   facades). No UI, no transport. It MUST be drivable headless and exposes one
   clean API (commands in, events/results out). The core never imports the TUI
   and never imports any adapter.
2. **TUI front-end** - py_tvision plus the view layer; one driver of the core.
3. **ACP / IDE adapter** - a *separate* front-end so IntelliJ and VS Code drive
   the *same* core over ACP (stdio), with no TUI involved.

Both the TUI and the ACP adapter sit on the one core API; neither leaks into
the core. This is "one core, many faces" (the same pattern as rex's panel
reducer; rex already speaks ACP). Phase 1 builds only layer 2's toolkit and a
demo; adding the ACP adapter later must touch only a thin adapter on the core,
not the core or the TUI. Concretely: `py_tvision/*` has **no** dependency on
`strelka.*` or on any core/runtime module (enforceable by a simple import test),
and the future Strelka core module imports neither `py_tvision` nor any
adapter.
