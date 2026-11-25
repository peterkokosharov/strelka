Превод от английския оригинал PY_TVISION_DESIGN.md; при разлика важи оригиналът.

# py_tvision - дизайн

Статус: чернова на дизайна, 2026-11-25. Нищо от описаното още не е изградено.

## 1. Цел и извън обхвата

**Цел.** Малка Python библиотека за текстов интерфейс (text UI) по духа на Turbo Vision (изгледи в дърво,
прозорци с рамка, лента с меню, статусен ред, модални диалози, мишка, цветни теми), която е достатъчно
добра, за да носи пълен Python порт на Layka ("Strelka") със същия външен вид и поведение като
C++ версията.

Твърди правила:
- Продукционен код: само стандартната библиотека на Python (Python >= 3.12). Без `curses` (CPython за Windows
  се доставя без `_curses`), без `textual`, `rich`, `pydantic`, `psutil`.
- Работи на Windows 10 1809+/11 (Windows Terminal, conhost), Linux, macOS.
- Независим дизайн (виж раздел 12). Не е превод на код на tvision с произход от Borland.

Извън обхвата (първа версия):
- Стари конзоли без VT изход (преди Windows 10 1809). Отказваме с ясно съобщение.
- Пълното API на tvision: без потоци/ресурси (`TStreamable`), без `TEditor`/`TMemo` с undo и
  търсене, без диалог за отваряне на файл, без outline view, без избор на цвят, без система за помощ, без валидатори.
- Управление на припокриващи се прозорци на работния плот отвъд необходимото (tile/cascade, списък с прозорци).
- База данни terminfo в стила на curses: ползваме фиксирано модерно подмножество на VT/xterm.
- GPM мишка на Linux конзолата (`/dev/tty1`), протоколът far2l, kitty keyboard protocol (по-късно, може би).

## 2. Какво Layka всъщност ползва от tvision (опис)

Преброено с grep върху `src/main.cpp` (2542 реда), `src/core.h`, `src/proc.*` на 2026-11-25.
`core.h` (1858 реда) е чиста логика (пренасяне на редове, markdown, редактиране на prompt, ширина, i18n) без
include на tvision; портва се в обикновен Python. Кодът, свързан с tvision, е приблизително редове 1200-2542 на `main.cpp`.

**Реферирани типове на tvision: ~33.** По брой препратки: `TRect` 50, `TColorAttr` 21, `TButton` 13,
`TDialog` 12, `TInputLine` 11, `TColor` 10, `TProgram` 8, `TPalette` 8, `TScrollBar` 7,
`TScreen` 6, `TEvent` 6, `TColorRGB` 6, `TStatusItem` 5, `TStaticText` 5, `TLabel` 5, `TView` 4,
`TStringCollection` 4, `TMenuBar` 4, `TDrawBuffer` 4, `TStatusLine` 3, `TSortedListBox` 3,
`TPoint` 3, `TColorBIOS` 3, `TChDirDialog` 3, `TApplication` 3, `TParamText` 2, `TListBox` 2,
`TStatusDef`, `TClipboard`, `TStringView`, `TSpan`, `TProgInit`, `TWindowInit` по 1-2; плюс
функцията `messageBox()` и `deskTop`.

**Собствените подкласове на Layka: 8.** `TLaykaApp` (TApplication: `idle`, `getPalette`),
`TLaykaDialog` (TDialog на цял екран: `handleEvent`, `calcBounds`, `changeBounds`),
`TPermDialog` (TDialog: `handleEvent`), `TMsgListBox` (TListBox: собствен `draw` с класове цвят за всеки ред
и вградени кодови фрагменти), `TPromptBox` (TView: 3-редово многоредово поле за въвеждане с пренасяне на редове,
история, клик с мишка, поставяне), `TInfoBar` (TMenuBar без меню: един информационен ред),
`TStatusParam` (TParamText с "горещ" цвят), `TChronoStringCollection` (несортирани данни за списък).
Припокривания: `draw` 4, `handleEvent` 4, `getPalette` 2, `setState` 1, `calcBounds`/`changeBounds` 1.

**Команди: 18.** Собствени: `cmSend, cmStop, cmResetCtx, cmPickModel, cmPickFolder, cmModelsReady,
cmOpenImage, cmCopyAnswer, cmKeysHelp, cmPermOnce, cmPermAlways, cmPermDeny` (12). Стандартни:
`cmOK, cmCancel, cmQuit, cmYes, cmMenu` (+ неявното `cmScreenChanged` при промяна на размера).

**Събития:** `evKeyDown`, `evCommand`, `evMouseDown`, плюс `putEvent` от `idle()` (приключило
изтегляне на моделите) и поставяне (paste) като един пакет (`kbPaste` + `textEvent`). **Кодове на клавиши: 37** различни (`kbAlt*` 15,
стрелки/Home/End/PgUp/PgDn, `kbCtrlHome/End`, `kbEsc`, `kbF1`, `kbF10`, `kbBack`, `kbDel`,
`kbAltEnter`, `kbCtrlEnter`, `kbCtrlJ`). Клавишите Alt+буква трябва да работят и при нелатински подредби
(Windows: по virtual key).

**Флагове/възможности:** `growMode` 13 употреби (`gfGrowLoX/HiX/LoY/HiY`: оформлението се строи на 80x25 и
се разтяга при промяна на размера), `sfSelected/sfFocused/sfActive/sfCursorVis`, `ofSelectable|ofFirstClick`,
`wfMove` изчистен, `bfDefault/bfNormal`, `mfConfirmation|mfYesButton|mfNoButton`.
API за рисуване: `getColor` 13, `drawView` 13, `moveStr` 9, `moveChar` 6, `writeLine` 4,
`setCursor` 3. Модално: `execView` 5 (вложено: диалог за разрешение се отваря от `idle()`, докато друг
модален цикъл работи), `endModal` 4. Цвят: директен RGB (`0x0000AF`, `0x003A3A`), резервен BIOS 16-цветен
вариант, получер шрифт, проверка с `TScreen::screenMode` за 256/true colour. Клипборд: `TClipboard::setText`
(системен клипборд, резервен OSC 52). Unicode: навсякъде UTF-8, широки CJK знаци (има UI език `zh`),
маркери за бърз клавиш `~X~` в етикети/бутони от `lang/*.ini`.

**Не се ползва:** падащи менюта (лентата с меню е само информационен ред; F10 не прави нищо), `TEditor`,
`TMemo`, `TFileDialog`, отметки (check box), радио бутони, списъци с история, валидатори, преместване/преоразмеряване
на прозорец с мишка, няколко прозореца на работния плот, потоци.

И така, подмножеството на Layka е: приложение + работен плот + един диалог на цял екран + модални диалози, бутон,
етикет, статичен/параметричен текст, едноредово поле за въвеждане, списък (сортиран, с type-ahead), лента за превъртане, статусен ред,
информационен ред, message box, избор на папка, собствен многоредов изглед за въвеждане, клипборд, кликове с мишка,
промяна на размера, нишки, които подават към UI. Демото във фаза 1 добавя истинско падащо меню, защото
библиотека, подобна на Turbo Vision, без такова е играчка.

## 3. Архитектура, взета от tvision (поведение, не код)

- **Дърво от изгледи.** Всяко видимо нещо е изглед (view) с граници спрямо неговия собственик. Групата притежава дъщерни
  изгледи в z-ред и ги рисува отзад напред с изрязване; прозорецът и диалогът са групи
  с рамка; приложението е група от лента с меню, работен плот и статусен ред.
- **Маршрутизиране на събития в три фази.** Събитията от мишката отиват към най-горния изглед под показалеца.
  Събитията от клавиатурата и командите отиват към фокусираната верига ("текущото" дете на всяко ниво, чак до
  листа), но изгледите, отбелязани като pre-process, ги виждат преди фокусираната верига, а post-process изгледите -
  след нея (така бутоните реагират на Alt-бързи клавиши, а статусният ред - на F-клавишите). Необработеното
  събитие се връща нагоре; приложението превръща необработените клавиши на елементите на статусния ред в команди.
- **Команди.** Цели числа, подавани като събития; изгледите могат да разрешават/забраняват команди глобално (забранените
  бутони и елементи на меню посивяват).
- **Модален цикъл.** `exec_view(dialog)` вмъква изгледа, върти вложен цикъл на събитията до
  `end_modal(cmd)`, премахва го и връща `cmd`. Влагането е позволено (Layka разчита на него).
- **Idle.** Когато няма чакащо събитие, цикълът вика `idle()` (Layka източва опашката си със съобщения,
  върти индикатор за изчакване на 10 Hz, отваря опашкирани диалози за разрешение).
- **Промяна на размера.** Платформата съобщава нов размер; приложението променя размера си и всяко дете
  се преизчислява според своя grow mode; след това пълно прерисуване.
- **Палитри.** tvision преобразува индекса на цвета на изгледа през палитрата на всеки собственик до
  байт от палитрата на приложението. Заместваме това с именувани роли в темата (раздел 7): по-просто за четене и промяна.
- **Екран.** Изгледите пишат клетки в един буфер извън екрана; flush го сравнява с това, което терминалът
  показва, и изпраща само променените серии (tvision `dispbuff.cpp`, magiblot).

## 4. Разположение на модулите

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

## 5. Платформен слой (механизми от стандартната библиотека за всяка ОС)

Общ интерфейс: `start()` (влизане в raw режим, алтернативен екран, включена мишка, скрит курсор),
`stop()` (възстановява точно запазеното), `size()`, `read(timeout) -> list[Event]`,
`write(str)`, `wake()` (може да се вика от всяка нишка), `set_clipboard(text)`.

**Windows (`platform/win32.py`, `ctypes` + `ctypes.wintypes`).**
- Handle-и: `GetStdHandle(STD_INPUT_HANDLE / STD_OUTPUT_HANDLE)`; отказ, ако не е конзола
  (`GetConsoleMode` не успее), напр. когато изходът е пренасочен.
- Запазват се входният/изходният режим и кодовите страници; при старт: входен режим `ENABLE_WINDOW_INPUT |
  ENABLE_MOUSE_INPUT | ENABLE_EXTENDED_FLAGS`, изчистват се `ENABLE_PROCESSED_INPUT` (Ctrl-C като клавиш),
  `ENABLE_LINE_INPUT`, `ENABLE_ECHO_INPUT`, `ENABLE_QUICK_EDIT_MODE` (иначе мишката избира
  текст). Изходен режим `ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING`, изчиства се
  `ENABLE_WRAP_AT_EOL_OUTPUT`; `DISABLE_NEWLINE_AUTO_RETURN`. Ако VT не може да се включи: спиране със
  съобщение (извън обхвата). `SetConsoleOutputCP(65001)`, `SetConsoleCP(65001)`.
- Вход: `WaitForMultipleObjects([hIn, hWakeEvent], timeout)` (без активно чакане; `wake()` вика
  `SetEvent` от работни нишки), после `GetNumberOfConsoleInputEvents` + `ReadConsoleInputW` в
  масив `INPUT_RECORD`. Декодират се `KEY_EVENT` (само натискане; `wVirtualKeyCode`,
  `uChar.UnicodeChar`, `dwControlKeyState`), `MOUSE_EVENT` (бутони, колелце чрез
  `MOUSE_WHEELED`, движение), `WINDOW_BUFFER_SIZE_EVENT` -> промяна на размера (размерът на *прозореца* се чете наново от
  `GetConsoleScreenBufferInfo.srWindow`, не размерът на буфера).
- Подробности при декодиране на клавиши: Alt+буква по virtual key, така че да работи при кирилска/гръцка подредба
  (Layka има нужда от това); AltGr идва като `RIGHT_ALT|LEFT_CTRL` и трябва да даде знака, а не
  Alt; UTF-16 суперогатни двойки идват като два записа; Alt+numpad и мъртвите клавиши дават текст
  само в записа за отпускане на клавиша.
- Поставяне (paste): `ReadConsoleInputW` няма bracketed paste. Евристика: печатаеми записи на клавиши, които вече
  чакат в един пакет (повече от няколко, въведени по-бързо от човек), се сливат в едно събитие за поставяне;
  нов ред вътре в него остава текст (правилото на Layka). Windows Terminal предлага и VT вход
  (`ENABLE_VIRTUAL_TERMINAL_INPUT`) с истински bracketed paste; оставя се като по-късна възможност, която преизползва
  `vtinput.py`.
- Изход: един `WriteConsoleW` (или `os.write` на UTF-8 байтове) на кадър; алтернативен екран с
  `ESC[?1049h` (поддържа се от conhost на Windows 10 1809+ и от Windows Terminal).
- Клипборд: `OpenClipboard`, `EmptyClipboard`, `GlobalAlloc/GlobalLock`, `SetClipboardData
  (CF_UNICODETEXT)`; чете се по същия начин за поставяне от меню.
- Възстановяване: `try/finally` + `atexit` + `SetConsoleCtrlHandler` за затваряне/излизане от системата.

**POSIX (`platform/posix.py`).** `termios` + флагове като при `tty.setraw` върху `/dev/tty` (или stdin, ако е
tty); атрибутите се запазват и се възстановяват при изход. `select.select([tty_fd, wake_pipe_r], [], [], timeout)`;
`os.pipe()` като self-pipe, в което пишат `wake()` и обработчикът на `SIGWINCH` (`signal.signal`); размерът
идва от `os.get_terminal_size`. Стартова последователност: алтернативен екран `?1049h`, скрит курсор, мишка
`?1000h ?1002h ?1006h` (SGR), bracketed paste `?2004h`, `?1036h` (meta изпраща ESC); при спиране се прави обратното.
Байтовете минават през `codecs.getincrementaldecoder('utf-8')(errors='replace')` и `vtinput.py`.
Неяснота с ESC: самотен ESC е клавиш само след ~40 ms без следващ байт. Клипборд: OSC 52
(`ESC]52;c;<base64>BEL`) по подразбиране; по избор `pbcopy` / `wl-copy` / `xclip` чрез `subprocess`,
когато са налични (проверка с `shutil.which`). `SIGTSTP`/`SIGCONT`: възстановяване и повторно влизане.

**`vtinput.py`** декодира CSI и SS3 последователности (`ESC[A`, `ESC[1;5H`, `ESC[3~`, `ESCOP`...), параметъра
за модификатор на xterm (2=Shift .. 8=Ctrl+Alt+Shift), `ESC` + клавиш като Alt, SGR мишка
`ESC[<b;x;yM/m` (бутони, колелце 64/65, бит за влачене 32), bracketed paste `ESC[200~ ... ESC[201~`, и
само прости режими без `ESC[?u`. Управлявано от таблица, ~60 записа.

**Ширина (`text.py`).** `unicodedata.east_asian_width(ch) in ('W','F')` -> 2; комбиниращи знаци
(`unicodedata.combining`, категории `Mn`, `Me`) и знаци с нулева ширина (`Cf`, ZWJ, variation selectors)
-> 0; управляващи знаци -> заместват се. Емоджи с VS16 се броят за 2. Една клетка държи графема (основа +
комбиниращ знак), така че комбиниращ знак никога не заема колона. Таблицата `cpWidth` в `core.h` на Layka (в стила на Markus
Kuhn) се ползва за кръстосана проверка в тестовете. Където терминалите не са съгласни (conhost и някои емоджита),
широк знак в последната колона се заменя с интервал, а следващият кадър прерисува целия
ред, щом той съдържа широк знак (евтина застраховка срещу разместване).

## 6. Модел на събитията

`Event(kind, key, mods, text, mouse_pos, buttons, command, info)` с видове `KEY`, `MOUSE_DOWN`,
`MOUSE_UP`, `MOUSE_MOVE`, `MOUSE_WHEEL`, `COMMAND`, `BROADCAST`, `PASTE`, `RESIZE`. Клавишите са
имена от `Key` плюс битове за модификатори (`ALT`, `CTRL`, `SHIFT`), а не пакетирани scan кодове; `key_code("Alt+Q")`
помага за таблиците. Командите са цели числа в `IntEnum` за стандартния набор, приложенията добавят свои над
1000. `Event.clear()` отбелязва събитието като обработено.

Една UI нишка притежава всички изгледи. Работните нишки (четецът на rex, изтегляне на модели, помощници) само викат
`app.post(fn_or_event)`: `queue.SimpleQueue` плюс `terminal.wake()`. Цикълът е:

```
while running:
    events = terminal.read(timeout=next_timer_or_idle)
    for ev in events + posted: route(ev)
    if nothing happened: idle(); timers
    if screen.dirty: flush (at most ~60 frames/s)
```

`exec_view()` върти същия цикъл вложено до `end_modal()`; `idle()` се вика и във вложените цикли.
Таймерите (`app.every(0.1, fn)`) заместват ръчно писаните проверки на часовник в `idle()`.

## 7. Рисуване, цвят и тема

**Буфер.** Екранът е списък от редове; всеки ред е два успоредни списъка `chars` (низ за клетка,
`""` за дясната половина на широк знак) и `attrs` (малък int индекс в таблица от интернирани `Style`).
Изгледите рисуват през `DrawContext`, изрязан до видимия им правоъгълник; групите изрязват децата си.
Пълното прерисуване на дървото от изгледи в задния буфер е по подразбиране; следенето на повредени редове спестява работа
за редове, които никой не е пипал. `draw_view()` от уиджет само го маркира като мръсен; рисуването става веднъж на
оборот на цикъла (слива поток от токени със стотици обновявания в секунда в един кадър).

**Flush/diff.** За всеки ред: ако `back.chars == front.chars and back.attrs == front.attrs` (сравнение на
списъци със скоростта на C) се пропуска; иначе се намират променените серии, излъчва се преместване на курсора `ESC[y;xH`, SGR само когато стилът се променя,
текстът; за кадъра се изгражда един низ, който се записва наведнъж, обвит в синхронизиран изход
`ESC[?2026h ... ESC[?2026l` (игнорира се там, където не се поддържа; избягва разкъсване в Windows Terminal).
Курсор: показва се на позицията на курсора на фокусирания изглед, `ESC[?25h/l`, форма чрез `ESC[n q`.

**Дълбочина на цвета.** Откриване: `COLORTERM=truecolor|24bit`, `WT_SESSION` (Windows Terminal), конзола на Windows
с VT -> 24-bit; `TERM` съдържа `256color` -> 256; иначе 16. Презаписване с променлива на средата /
ключ в ini (`colors = 16|256|24bit`). `color.py` преобразува RGB до най-близкия запис на xterm-256
(куб 6x6x6 + сива скала, по квадрат на разстоянието с нещо като перцептивно тегло) и до 16 цвята чрез
групи по нюанс/светлина. Собствен код; подходът HCL на `colors.cpp` на magiblot (MIT) може да се портва, ако
простото преобразуване изглежда грешно.

**Теми.** Темата е речник `role -> Style`. Ролите са имена, напр. `desktop`, `window.frame`,
`window.frame.active`, `window.title`, `dialog.body`, `button`, `button.default`,
`button.focused`, `button.hotkey`, `button.shadow`, `input`, `input.selected`, `input.arrows`,
`list`, `list.focused`, `list.selected`, `scrollbar`, `menu`, `menu.selected`, `menu.hotkey`,
`menu.disabled`, `status`, `status.hotkey`, `label`, `label.hotkey`, `shadow`. Уиджетите искат
роля; изгледът може да презапише роли локално (класовете на списъка със съобщения на Layka `msg.you`, `msg.rex`,
`msg.code`, `msg.diff.add` ... също стават роли).
Вградени теми:
- `classic` - външният вид на Turbo Vision: сиви диалози, циан/син работен плот, зелени бутони, черни сенки.
  Цветовете са избрани от нас, не са копирани от низовете с байтове на палитрата на Borland.
- `modern` - същото оформление и рисуване на рамки, тъмен шистов фон, един акцентен цвят, по-меки сиви;
  силно контрастните полета за въвеждане на Layka (бяло върху `#0000AF`) както в C++ версията.
- `mono` - за 16-цветни терминали или такива без цвят (`NO_COLOR` се зачита).
Важни подробности на "fason" (външния вид): двойна рамка за активния прозорец, единична за неактивните; заглавие
центрирано с интервали; бутони със сянка от полублокове (`▄`/`▀`) и анимация при натискане; сянка
на прозореца, рисувана чрез затъмняване на клетките под него (не черни блокове); стрелки `▲▼◆` и писта на лентата за превъртане `░▒`;
резервен ASCII набор (`+-|#`), когато изходът не е UTF-8.

## 8. Набор от уиджети (минимален, според Layka + демото)

| Widget | Нужен на | Бележки |
|---|---|---|
| Application, Desktop | всички | информационен ред отгоре, статусен ред отдолу |
| Window, Dialog, Frame | главен изглед, всички диалози | бутон за затваряне, преместване не е нужно на Layka; влачене във фаза 3 |
| Button | 13 препратки | подразбиращият се бутон приема Enter; бърз клавиш `~X~`; забранено състояние |
| Label, StaticText, ParamText | етикети, помощен текст, статус | Label фокусира свързания си изглед |
| InputLine | endpoint, модел, работна папка | хоризонтално превъртане, селекция, Ctrl-C/V/X, максимален брой знаци |
| ScrollBar | списъци | свързана със списъчните изгледи |
| ListBox, SortedListBox | съобщения, модели, подробности за разрешение | собствена кука за рисуване на елемент, type-ahead |
| TextBox (многоредов) | prompt | родова версия на TPromptBox; логика от PromptEdit в core.h |
| StatusLine, InfoLine | долен/горен ред | таблица клавиш -> команда, подсказки |
| MenuBar, MenuBox | демо (Layka може да го приеме по-късно) | Alt-буква, F10, мишка, подменюта на едно ниво |
| message_box | потвърждение при изход | Yes/No/OK/Cancel |
| FolderDialog | избор на работна папка | наш собствен прост дизайн: поле за път + списък с папки + списък с дискове на Windows |
| Clipboard | Alt-C | системен клипборд, резервен OSC 52 |

## 9. Трудни части и рискове

1. **Вярност на входа в Windows.** Alt срещу AltGr, нелатински подредби, мъртви клавиши, суперогатни двойки, откриване на
   поставяне без bracketed paste, Ctrl-Enter/Alt-Enter (Windows Terminal взема Alt-Enter за
   цял екран, освен ако настройката е изключена), загубена мишка, когато потребителят пак включи QuickEdit.
   Смекчаване: демо с ехо на клавиши/мишка от първия ден, записани фикстури `INPUT_RECORD` в тестовете.
2. **Разлики между терминалите.** Windows Terminal (добър: true colour, мишка, синхронизиран изход);
   conhost (VT работи на Win10 1809+, true colour има, някои ширини на емоджита са грешни, по-бавен);
   терминалът на IntelliJ (JediTerm; върви през ConPTY на Windows, мишката и Alt клавишите частично се изяждат
   от IDE, true colour е наред); терминалът на VS Code (xterm.js: добър, но Ctrl/Alt комбинациите може да бъдат
   прихванати от VS Code; F1 отваря командната му палитра). macOS Terminal.app: само 256 цвята, без
   true colour -> трябва да се понижава. Смекчаване: презаписване на дълбочината на цвета, клавишите винаги достъпни и
   с втора комбинация (Layka вече има Alt-Q и Alt-X), ръчна тестова матрица за всяка версия.
3. **Широки и сложни знаци.** CJK етикети (`zh`), емоджита в изхода на модела, комбиниращи знаци;
   терминалът и нашата таблица за ширина може да не са съгласни, което оставя разместени редове. Смекчаване в раздел 5; тестове
   с CJK/емоджи/комбиниращи низове срещу ширините от `core.h`.
4. **Производителност в чист Python.** 200x60 = 12 000 клетки. Бюджет: пълно рисуване на дървото + diff под
   10 ms на лаптоп. Смекчаване: сравнение на списъци на ниво ред, интернирани стилове, флаг за мръсно с таван на кадрите, без обекти
   за клетка, списъчните изгледи рисуват само видимите редове, пренасянето на съобщения се прави веднъж за
   запис (Layka вече го прави). Измерва се във фаза 1 със стрес демо (бърз поток от токени).
5. **Възстановяване на терминала при всеки изход** (изключение, Ctrl-Break, SIGTERM, затворен прозорец).
   Счупен терминал след срив е най-лошото първо впечатление. Смекчаване: един контекстен мениджър `Terminal`, `atexit`, обработчици на сигнали и
   на конзолни събития, тест на срив в CI на POSIX с `pty`.
6. **Нишки.** Само UI нишката пипа изгледите; всичко друго минава през `post()`.
   Нарушението разваля екрана тихо; проверка при дебъг утвърждава id-то на нишката в `draw_view()`.
7. **Разпълзяване на обхвата към пълния tvision.** Таблицата в раздел 8 е обхватът; всичко друго изисква
   първо случай на употреба в Layka.

## 10. Оценка на размера (редове Python, без тестове)

| Модул | LOC |
|---|---|
| geometry.py | 80 |
| text.py (ширина, изрязване, бързи клавиши) | 200 |
| color.py | 150 |
| theme.py (роли + 3 теми) | 220 |
| screen.py (буфер, draw context, diff/flush) | 400 |
| events.py | 180 |
| views.py (View, Group, маршрутизиране, фокус, grow modes, модално) | 800 |
| window.py (Frame, Window, Dialog, сянка) | 300 |
| app.py (Program, Desktop, цикли, idle, таймери, промяна на размера) | 300 |
| platform/__init__ + headless | 180 |
| platform/vtinput.py | 350 |
| platform/win32.py | 550 |
| platform/posix.py | 250 |
| widgets: static 120, button 160, inputline 320, scrollbar 180, listview 380, textbox 350 | 1,510 |
| widgets: menu (bar, box, status, info) 550, msgbox 120, folderdlg 250 | 920 |
| demo/ | 250 |
| **Общо библиотека** | **~6,600** |

Тестове: още около 2 500. За сравнение: Strelka отгоре (логиката на `core.h` ~1 500 реда Python,
UI ~1 000, процес/мост ~600) е отделна оценка от ~3 000.

## 11. Стратегия за тестване

Само поведение и интеграция; без тестове за getter-и, dataclass-ове или константи.
- **Headless snapshot тестове.** `platform/headless.py` дава терминал с произволен размер; тестът изгражда
  дърво от изгледи, подава събития и сравнява екрана със златен текстов файл (знаци) плюс
  компактна карта на стиловете (една буква за роля). Златните файлове живеят в `tests/snapshots/`, четат се в
  diff и се прегенерират само нарочно (`--update-snapshots`).
- **Round-trip тест на рисуването.** Малък VT интерпретатор (само за тестове) прилага изхода на flush върху
  празна мрежа; резултатът трябва да е равен на задния буфер след случайни поредици от рисувания. Това пази
  кода за diff/flush, най-рисковата част, породена от съображения за производителност.
- **Таблици за декодера на входа.** Последователности от байтове -> събития за `vtinput.py` (клавиши с модификатори, SGR
  мишка, поставяне, разделено на няколко четения, самотен ESC); синтетични структури `INPUT_RECORD` -> събития за
  `win32.py` (декодерът е чиста функция и работи на всяка ОС; само четецът изисква Windows).
- **Сценарии на поведение.** Ред на Tab и Alt-бързи клавиши, подразбиращ се бутон при Enter, модален диалог
  връща командата си, вложен модален от `idle()`, преоформяне при промяна на размера чрез grow modes (80x25 ->
  132x40 -> обратно), type-ahead и превъртане в списък, пренасяне на ред в текстово поле с CJK и емоджи, поставяне на
  многоредов текст, подадени събития от работна нишка.
- **Тест с истински терминал (POSIX, само за тестове).** `pty.fork()` пуска демото, изпраща клавиши, проверява дали
  терминалът е възстановен (`stty -a` еднакъв преди/след), също и след принудително изключение.
- **Ръчна матрица за всяка версия.** Windows Terminal, conhost, IntelliJ, VS Code, терминал на Linux,
  macOS Terminal.app; списък от 15 точки (рамки, цветове, клик с мишка, колелце, Alt клавиши, поставяне,
  промяна на размера, CJK, клипборд, възстановяване при изход).
- **Проверка на производителността.** Стрес режимът на демото печата времена на кадрите; тестът пада, ако пълно прерисуване на 200x60
  плюс flush надхвърли щедра граница.

## 12. Ред на изграждане

- **Фаза 0 - платформа и екран.** `geometry`, `text`, `color`, `screen`, `platform/*`,
  `vtinput`; демота: ехо на клавиши/мишка и цветова диаграма на Windows Terminal, conhost, Linux.
  Готово, когато: всеки клавиш от описа на Layka се декодира правилно и на двете ОС, терминалът се възстановява при срив.
- **Фаза 1 - работещо демо.** `events`, `views`, `window`, `app`, `theme` (classic + modern),
  уиджети button, label, static text, input line, scroll bar, list box, menu bar + menu box,
  status line, message box. Демо: работен плот с един прозорец; меню `File` (New window, Dialog...,
  Exit) и `Help` (About); статусен ред `F1 Help  Alt-X Exit`; диалог с input line с етикет,
  списък с лента за превъртане, OK/Cancel; кликове с мишка; промяна на размера. Snapshot тестове за всяко.
- **Фаза 2 - подмножеството на Layka е завършено.** Сортиран списък с type-ahead, param text, многоредово текстово поле,
  информационен ред, диалог за папка, клипборд, поставяне, вложен модален + idle + таймери + `post()`, mono
  тема, резервен ASCII. Макет на екран на Layka, управляван от фалшиви данни, съвпада с оформлението на C++.
- **Фаза 3 - шлифоване.** Влачене и преоразмеряване на прозорец, сенки чрез затъмняване, анимация при натискане, синхронизиран
  изход, презаписване на дълбочината на цвета, преглед на производителността, ръчна матрица на терминалите.
- **Фаза 4 - Strelka** отгоре (отделен план).

## 13. Лиценз

Факти от `tvision/COPYRIGHT`: Borland е публикувал оригиналния код на Turbo Vision само с
отказ от отговорност, без предоставяне на лиценз (правата най-вероятно днес са у Embarcadero). Промените на
magiblot и кодът, писан от нула, са под MIT (Copyright 2019-2025 magiblot).

Правила за py_tvision:
- **Файлове с произход от Borland: четат се само за поведение, никога не се превеждат.** Всички
  `tvision/source/tvision/*.cpp`, които носят "Copyright (c) 1994 by Borland International"
  (напр. `tview.cpp`, `tgroup.cpp`, `tprogram.cpp`, `tbutton.cpp`, `tinputli.cpp`, `tlstview.cpp`,
  `tchdrdlg.cpp`, `tscreen.cpp`, `tmenu*.cpp`, `tstatusl.cpp`, `msgbox.cpp`), файловете `.asm`
  и частите на Borland в `include/tvision/*.h`, включително низовете с байтове на палитрата
  (`cpAppColor`, `cpAppBlackWhite`, `cpAppMonochrome`): вместо това дефинираме собствени теми,
  базирани на роли, и собствени стойности на цветовете. Имената в Python са наши (`View`, `Group`, `exec_view`,
  `Event.KEY`), не копие заглавен файл по заглавен файл.
- **Файлове с произход magiblot (MIT): идеите могат да се портват, пази се неговото съобщение.** `source/platform/*`:
  `win32con.cpp`, `conctl.cpp`, `termio.cpp`, `ansiwrit.cpp`, `dispbuff.cpp`, `colors.cpp`,
  `winwidth.cpp`, `unixclip.cpp`, `sigwinch.cpp`, `events.cpp` и `tvision/tclipbrd.cpp`.
  Ако се портва код от тях, файлът получава ред "Parts derived from magiblot/tvision,
  Copyright 2019-2025 magiblot, MIT", а `py_tvision/LICENSES/tvision-MIT.txt` съдържа пълния текст.
- **Код на трети страни в platform/:** `strings.cpp` (Milo Yip, MIT) и `ttext.cpp`
  (UTF-8 декодерът на Bjoern Hoehrmann, MIT). Не са нужни: Python има `codecs` и `str`.
- py_tvision сам по себе си: MIT, автор Peter Kokosharov <peter.kokosharov@gmail.com>, както Layka.
- **Име:** "Turbo Vision" е име на продукт на Borland. "py_tvision" става като работно име;
  преди публично издание обмислете неутрално име (и напишете "inspired by Turbo Vision" в README).
