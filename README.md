# Strelka

Strelka is a text-mode coding-agent front-end for ai-rex, written in Python
with the standard library only. It is built on `py_tvision`, a small stdlib
TUI toolkit in the spirit of Turbo Vision that lives in this repository.

Strelka is the terminal front-end of a small family of tools: kiko (an LLM
gateway), rex (an agent runtime) and Layka (a C++ sibling client).

py_tvision is inspired by Turbo Vision. It is an independent stdlib
implementation and is not affiliated with Borland, Embarcadero or the
magiblot/tvision project.

Status: early. The `py_tvision` toolkit and the configuration layer are in
place; the agent front-end itself is still to come.

## Requirements

- Python 3.12 or newer
- No third-party runtime packages (standard library only)

## Layout

- `src/py_tvision/` the TUI toolkit (generic, no dependency on Strelka)
- `src/strelka/` the Strelka application layer (configuration so far)
- `examples/demo.py` a toolkit demo: menu bar, status line, window, dialog
- `tests/` the test suite
- `docs/` design notes for `py_tvision` (English, with a Bulgarian copy)

## Run the demo

    python examples/demo.py                  # classic theme
    python examples/demo.py --theme modern

`STRELKA_THEME` also selects the theme. Keys: F10 or Alt-F / Alt-H open the
menus, Tab moves focus, Esc closes a dialog or menu, Alt-X exits.

## Run the tests

Test tools (pytest, ruff, mypy) go into a virtual environment only:

    python -m venv .venv
    .venv/Scripts/pip install -e ".[dev]"    # Windows
    .venv/bin/pip install -e ".[dev]"        # Linux / macOS
    .venv\Scripts\python -m pytest -q    # Windows
    .venv/bin/python -m pytest -q         # Linux / macOS

## Configuration

Strelka reads `strelka.toml` from its config directory (`STRELKA_CONFIG_DIR`,
else `XDG_CONFIG_HOME/strelka`, else the per-OS default) and overrides from
environment variables `STRELKA_<SECTION>__<KEY>`. Secrets are never written
to the config file.

## License

MIT, see `LICENSE`.
