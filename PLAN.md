# Layka Python Port - План за реализация

## Цел
Преписване на Layka (C++ Turbo Vision) на Python с Textual TUI framework.
Същата функционалност: TUI за ai-rex (JSONL subprocess), многожезичен, конфигурируем.

---

## Архитектура (Python)

```
layka_py/
├── src/
│   └── layka/
│       ├── __init__.py
│       ├── __main__.py          # entry point: python -m layka
│       ├── config.py            # TOML config (kikolib.config)
│       ├── models.py            # Pydantic модели за JSONL протокол
│       ├── proc.py              # asyncio subprocess manager (kill-tree, JSONL)
│       ├── app.py               # Textual App клас
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── message_list.py  # Virtualized scrollable list (user/assistant/tool)
│       │   ├── input_line.py    # Input с history, completion
│       │   ├── status_bar.py    # Model, tokens, connection status
│       │   ├── menu_bar.py      # File, Edit, View, Model, Help
│       │   └── dialogs.py       # Model selector, settings, about
│       ├── i18n.py              # i18n от .ini файлове (съществуващите в ../lang)
│       ├── mermaid.py           # Mermaid -> SVG/PNG (playwright или kroki)
│       └── cli.py               # argparse за --version, --config, --lang
├── tests/
│   ├── test_config.py
│   ├── test_proc.py
│   ├── test_models.py
│   └── test_i18n.py
├── requirements.txt
├── requirements.lock
├── pyproject.toml
└── README.md
```

---

## JSONL Протокол (съществуващ - от C++ кода)

### Входящи (от rex -> layka)
```json
{"type": "token", "text": "..."}
{"type": "tool_call", "id": "...", "name": "...", "arguments": "..."}
{"type": "tool_result", "id": "...", "result": "...", "error": null}
{"type": "status", "state": "thinking|streaming|idle|error", "message": "..."}
{"type": "error", "message": "..."}
{"type": "done", "usage": {"prompt_tokens": 10, "completion_tokens": 50}}
```

### Изходящи (от layka -> rex)
```json
{"type": "chat", "messages": [...], "model": "...", "temperature": 0.7}
{"type": "cancel"}
{"type": "config", "key": "...", "value": "..."}
{"type": "list_models"}
```

---

## Фази и времеви рамки

### Фаза 0: Setup (0.5 седмица) ✅ ГОТОВО
- [x] Папка `py_port/`
- [x] `requirements.txt` с pinned версии
- [x] `pyproject.toml`
- [ ] venv + `pip install -r requirements.txt`
- [ ] `pytest` конфигурация

### Фаза 1: Core Logic (1.5 седмици)
| Задача | Файл | Оценка |
|--------|------|--------|
| Config system (TOML, env, defaults, validation) | `config.py` | 2 дни |
| Pydantic модели за JSONL протокол | `models.py` | 1 ден |
| i18n loader от `.ini` файлове | `i18n.py` | 1 ден |
| Unit тестове за горните | `tests/` | 1 ден |
| **Общо** | | **~5 работни дни** |

### Фаза 2: Process Layer (1.5 седмици)
| Задача | Файл | Оценка |
|--------|------|--------|
| Async subprocess manager (spawn, stdin/stdout/stderr) | `proc.py` | 3 дни |
| Kill-tree (POSIX: process group, Windows: job object) | `proc.py` | 2 дни |
| JSONL framing (read/write, backpressure) | `proc.py` | 1 ден |
| Reconnect / restart логика | `proc.py` | 1 ден |
| Unit + integration тестове | `tests/test_proc.py` | 1 ден |
| **Общо** | | **~8 работни дни** |

### Фаза 3: Textual UI - Скелет (2 седмици)
| Задача | Файл | Оценка |
|--------|------|--------|
| `App` клас, CSS, bindings | `app.py` | 2 дни |
| `MessageList` - virtualized, syntax highlight, markdown | `widgets/message_list.py` | 4 дни |
| `InputLine` - history, completion, multiline (Alt+Enter) | `widgets/input_line.py` | 2 дни |
| `StatusBar` - model, tokens, connection, clock | `widgets/status_bar.py` | 1 ден |
| `MenuBar` - File/Edit/View/Model/Help | `widgets/menu_bar.py` | 2 дни |
| Dialogs: ModelSelector, Settings, About | `widgets/dialogs.py` | 2 дни |
| **Общо** | | **~13 работни дни** |

### Фаза 4: Integration (1.5 седмици)
| Задача | Оценка |
|--------|--------|
| Свързване App <-> Proc (asyncio tasks, messages) | 3 дни |
| Mermaid viewer (render -> SVG -> показване в dialog) | 2 дни |
| Config load/save от UI | 1 ден |
| CLI args (--config, --lang, --version, --debug) | 1 ден |
| End-to-end тест с реален rex | 2 дни |
| **Общо** | **~9 работни дни** |

### Фаза 5: Polish & Pack (1 седмица)
| Задача | Оценка |
|--------|--------|
| PyInstaller spec (Linux, Windows, macOS) | 2 дни |
| Икони, .desktop файл, shortcuts | 1 ден |
| README, CHANGELOG, LICENSE | 1 ден |
| Edge cases: resize, encoding, large output, cancel | 2 дни |
| **Общо** | **~6 работни дни** |

---

## Общо време: ~6.5 седмици (part-time, ~1-2ч/ден = ~3-4 месеца)

---

## Зависимости (requirements.txt)

```txt
# Core
textual==8.2.8
rich==13.9.4
pygments==2.18.0
markdown-it-py==3.0.0
cssutils==2.7.0
typing-extensions==4.12.2

# Config & Data
pydantic==2.8.2
pydantic-settings==2.4.0
tomli-w==1.0.0  # за запис на config

# Process
psutil==5.9.8

# Mermaid rendering
playwright==1.45.0  # headless browser за mermaid -> SVG

# Testing
pytest==8.2.2
pytest-asyncio==0.23.3
pytest-mock==3.12.0

# Dev
ruff==0.5.0
mypy==1.10.0
```

---

## Рискове и митигация

| Риск | Вероятност | Митигация |
|------|------------|-----------|
| `MessageList` performance при 10k+ съобщения | Висока | Virtualization от начало, lazy rendering |
| Windows kill-tree | Висока | Тестване на Windows от ФАЗА 2, psutil fallback |
| Textual API промени | Ниска | Pin версия, не ползваме private API |
| Mermaid rendering (playwright е тежък) | Средна | Опционален feature, fallback към kroki API |
| i18n RTL (не е в план) | Ниска | Не поддържаме засега |

---

## Ключови решения

1. **kikolib.config** за конфигурация - вече е тестван в kiko
2. **Pydantic v2** за JSONL модели - бърз, type-safe
3. **asyncio subprocess** - стандартен, без трети страни
4. **Textual widgets** - не пишем свои, наследяваме и кастъмваме
5. **Playwright за Mermaid** - най-надежния рендеринг, headless
6. **PyInstaller за bundling** - стандарт за Python apps

---

## Следни стъпки (започваме утре)

1. Създаване на `requirements.txt` и `pyproject.toml`
2. `python -m venv .venv && pip install -r requirements.txt`
3. `config.py` - първи файл за имплементация
4. `pytest tests/test_config.py -v` - първи тест

---

*План създаден: 2025-11-25*
*Автор: Claude (по спецификация на потребителя)*
