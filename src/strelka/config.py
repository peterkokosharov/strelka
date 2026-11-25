# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Strelka configuration system (standard library only).

Load order, each layer overriding the previous one:

  1. built-in defaults (the dataclass field defaults below);
  2. values found in the TOML config file (``strelka.toml``);
  3. environment variables ``STRELKA_<SECTION>__<KEY>`` that are *actually set*.

The loader never raises: a missing file, malformed TOML or an out-of-range
value falls back to the default for that value and logs a warning (to a
module logger, never configured at import time).

Secrets (API keys, tokens, passwords) are never written to disk by
``save_config`` and never logged.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Keys whose values must never be written to disk or logged.
_SECRET_KEYS = frozenset({"api_key", "apikey", "token", "secret", "password", "authorization"})


# --- Paths -----------------------------------------------------------------

def config_dir() -> Path:
    """Return the per-OS configuration directory.

    Priority: ``$STRELKA_CONFIG_DIR`` > ``$XDG_CONFIG_HOME/strelka`` > per-OS
    default (Windows ``%APPDATA%\\strelka``, macOS
    ``~/Library/Application Support/strelka``, otherwise ``~/.config/strelka``).
    """
    env = os.environ.get("STRELKA_CONFIG_DIR")
    if env:
        return Path(env).expanduser()

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "strelka"

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "strelka"
        return Path.home() / "AppData" / "Roaming" / "strelka"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "strelka"

    return Path.home() / ".config" / "strelka"


def config_file() -> Path:
    """Path to the single config file, ``strelka.toml``."""
    return config_dir() / "strelka.toml"


def lang_dir() -> Path:
    """Directory holding the language ``.ini`` files.

    Priority: ``$STRELKA_LANG_DIR`` (or ``$LAYKA_LANG_DIR``,
    the language files shared with the C++ sibling Layka) > ``<config_dir>/lang`` if present >
    packaged ``lang`` next to the installed package > source-tree ``lang`` >
    ``<config_dir>/lang`` (even when it does not yet exist).
    """
    env = os.environ.get("STRELKA_LANG_DIR") or os.environ.get("LAYKA_LANG_DIR")
    if env:
        return Path(env).expanduser()

    candidate = config_dir() / "lang"
    if candidate.is_dir():
        return candidate

    here = Path(__file__).resolve()
    for up in (here.parent.parent.parent, here.parent.parent.parent.parent):
        pkg = up / "lang"
        if pkg.is_dir():
            return pkg

    return config_dir() / "lang"


# --- Dataclasses -----------------------------------------------------------

@dataclass
class RexConfig:
    """ai-rex subprocess configuration."""

    command: list[str] = field(default_factory=lambda: ["python", "-m", "rex"])
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    startup_timeout: float = 10.0
    shutdown_timeout: float = 5.0
    restart_on_crash: bool = True
    max_restarts: int = 3
    restart_delay: float = 2.0


@dataclass
class UIConfig:
    """UI appearance and behaviour."""

    language: str = "en"  # en, bg, de, fr, ru, zh
    theme: str = "auto"  # dark, light, auto
    show_line_numbers: bool = True
    word_wrap: bool = True
    syntax_highlight: bool = True
    markdown_render: bool = True
    mermaid_render: bool = True
    scrollback_limit: int = 10000
    font_size: int = 0  # 0 = terminal default


@dataclass
class ModelConfig:
    """Default model parameters."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    file: str | None = None  # None = stderr only
    max_bytes: int = 1_000_000
    backup_count: int = 3


@dataclass
class StrelkaConfig:
    """Complete Strelka configuration."""

    rex: RexConfig = field(default_factory=RexConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


_SECTIONS: dict[str, type] = {
    "rex": RexConfig,
    "ui": UIConfig,
    "model": ModelConfig,
    "logging": LoggingConfig,
}


# --- Validation ------------------------------------------------------------

_ENUMS: dict[tuple[str, str], frozenset[str]] = {
    ("ui", "theme"): frozenset({"dark", "light", "auto"}),
    ("logging", "level"): frozenset({"DEBUG", "INFO", "WARNING", "ERROR"}),
}

_RANGES: dict[tuple[str, str], tuple[float, float]] = {
    ("model", "temperature"): (0.0, 2.0),
    ("model", "top_p"): (0.0, 1.0),
    ("model", "presence_penalty"): (-2.0, 2.0),
    ("model", "frequency_penalty"): (-2.0, 2.0),
}


def _coerce_field(section: str, key: str, declared: type, value: Any) -> Any:
    """Coerce ``value`` to the field's declared type, raising on mismatch."""
    origin = declared
    # Strip Optional/typed containers down to a runtime-checkable base type.
    name = getattr(declared, "__name__", str(declared))
    if name == "list" or getattr(declared, "__origin__", None) is list:
        if not isinstance(value, list):
            raise ValueError(f"{section}.{key} must be a list, got {type(value).__name__}")
        return [str(v) for v in value]
    if name == "dict" or getattr(declared, "__origin__", None) is dict:
        if not isinstance(value, dict):
            raise ValueError(f"{section}.{key} must be a table")
        return {str(k): str(v) for k, v in value.items()}
    if origin is bool:
        if not isinstance(value, bool):
            raise ValueError(f"{section}.{key} must be true/false")
        return value
    if origin is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{section}.{key} must be an integer")
        return value
    if origin is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{section}.{key} must be a number")
        return float(value)
    if origin is str:
        if not isinstance(value, str):
            raise ValueError(f"{section}.{key} must be a string")
        return value
    # Optional / unions (str | None, int | None): accept None or coerce str.
    if value is None:
        return None
    return value


def _build_section(section: str, cls: type, values: dict[str, Any]) -> Any:
    """Build one section dataclass, validating every provided key."""
    kwargs: dict[str, Any] = {}
    valid = {f.name: f.type for f in fields(cls)}
    for key, raw in values.items():
        if key not in valid:
            log.warning("Unknown config key %s.%s ignored", section, key)
            continue
        declared = valid[key]
        declared_t = _declared_base(cls, key)
        coerced = _coerce_field(section, key, declared_t, raw)
        enum = _ENUMS.get((section, key))
        if enum is not None and coerced not in enum:
            raise ValueError(f"{section}.{key} must be one of {sorted(enum)}, got {coerced!r}")
        rng = _RANGES.get((section, key))
        if rng is not None and coerced is not None and not (rng[0] <= coerced <= rng[1]):
            raise ValueError(f"{section}.{key} must be in [{rng[0]}, {rng[1]}], got {coerced}")
        kwargs[key] = coerced
    return cls(**kwargs)


def _declared_base(cls: type, key: str) -> type:
    """Return a runtime-usable declared type for a dataclass field.

    Dataclass ``f.type`` may be a string under ``from __future__ import
    annotations``; map the known field names to concrete types.
    """
    hints = {
        "command": list,
        "cwd": str,
        "env": dict,
        "startup_timeout": float,
        "shutdown_timeout": float,
        "restart_on_crash": bool,
        "max_restarts": int,
        "restart_delay": float,
        "language": str,
        "theme": str,
        "show_line_numbers": bool,
        "word_wrap": bool,
        "syntax_highlight": bool,
        "markdown_render": bool,
        "mermaid_render": bool,
        "scrollback_limit": int,
        "font_size": int,
        "model": str,
        "temperature": float,
        "max_tokens": int,
        "top_p": float,
        "presence_penalty": float,
        "frequency_penalty": float,
        "level": str,
        "file": str,
        "max_bytes": int,
        "backup_count": int,
    }
    return hints.get(key, str)


# --- Loader ----------------------------------------------------------------

def _read_file(path: Path) -> dict[str, Any]:
    """Read the TOML config file, returning {} on any problem (with a warning)."""
    if not path.is_file():
        log.debug("Config file not found: %s", path)
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except Exception as exc:  # malformed TOML, permission error, ...
        log.warning("Failed to parse %s: %s; using defaults", path, exc)
        return {}


def _env_overlay() -> dict[str, dict[str, Any]]:
    """Collect ``STRELKA_<SECTION>__<KEY>`` env vars that are actually set.

    Only variables that exist are returned, so unset env never overwrites a
    file value. List/dict values may be given as a JSON string.
    """
    out: dict[str, dict[str, Any]] = {}
    for env_name, raw in os.environ.items():
        if not env_name.startswith("STRELKA_") or "__" not in env_name:
            continue
        body = env_name[len("STRELKA_"):]
        section, _, key = body.partition("__")
        section = section.lower()
        key = key.lower()
        if section not in _SECTIONS:
            continue
        declared = _declared_base(_SECTIONS[section], key)
        out.setdefault(section, {})[key] = _parse_env_value(declared, raw)
    return out


def _parse_env_value(declared: type, raw: str) -> Any:
    """Parse an env string into the declared type (JSON for list/dict)."""
    if declared in (list, dict):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fall back to comma split for a bare list.
            if declared is list:
                return [part.strip() for part in raw.split(",") if part.strip()]
            return raw
    if declared is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if declared is int:
        try:
            return int(raw)
        except ValueError:
            return raw
    if declared is float:
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw


def load_config() -> StrelkaConfig:
    """Load the configuration from defaults + file + environment.

    Never raises. The known overlay bug is fixed here: the file layer and the
    env layer each contribute *only the keys they actually provide*, so a
    default can never clobber a file value and an unset env var can never
    clobber a file value.
    """
    file_layer = _read_file(config_file())
    env_layer = _env_overlay()

    cfg_sections: dict[str, Any] = {}
    for section, cls in _SECTIONS.items():
        merged: dict[str, Any] = {}

        raw_file = file_layer.get(section, {})
        if section == "rex" and isinstance(raw_file, list):
            raw_file = {"command": raw_file}  # [rex] given as a bare array
        if isinstance(raw_file, dict):
            merged.update(raw_file)

        merged.update(env_layer.get(section, {}))

        try:
            cfg_sections[section] = _build_section(section, cls, merged)
        except Exception as exc:
            log.warning("Config validation failed for [%s]: %s; using defaults", section, exc)
            cfg_sections[section] = cls()

    return StrelkaConfig(**cfg_sections)


def _strip_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` with any secret-looking keys removed."""
    clean: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _SECRET_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = _strip_secrets(value)
        else:
            clean[key] = value
    return clean


def _toml_dump(data: dict[str, Any]) -> str:
    """Tiny TOML writer (stdlib has no writer) for the flat section layout."""
    lines: list[str] = []
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)  # safe quoting/escaping, TOML-compatible basic string
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items())
        return "{" + inner + "}"
    return json.dumps(str(value))


def save_config(cfg: StrelkaConfig) -> None:
    """Write the configuration to the config file (creating the directory).

    Secret-looking keys and ``None`` values are stripped; nothing is logged
    at value level.
    """
    data = asdict(cfg)
    data = _strip_secrets(data)
    # Drop None values (TOML has no null) and empty optionals.
    for section in list(data):
        if isinstance(data[section], dict):
            data[section] = {k: v for k, v in data[section].items() if v is not None}

    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_toml_dump(data), encoding="utf-8")
    log.info("Configuration saved to %s", path)


# --- Singleton accessor ----------------------------------------------------

_config: StrelkaConfig | None = None


def get_config() -> StrelkaConfig:
    """Return the cached config instance (loading it on first call)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> StrelkaConfig:
    """Force a reload and refresh the cache."""
    global _config
    _config = load_config()
    return _config


# --- Convenience getters ---------------------------------------------------

def rex_command() -> list[str]:
    return get_config().rex.command


def ui_language() -> str:
    return get_config().ui.language


def default_model() -> str:
    return get_config().model.model
