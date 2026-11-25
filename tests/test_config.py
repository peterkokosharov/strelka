# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8, claude-opus-5-5
"""Tests for strelka.config (standard-library, dataclass based)."""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from strelka.config import (  # noqa: E402
    StrelkaConfig,
    LoggingConfig,
    ModelConfig,
    RexConfig,
    UIConfig,
    config_dir,
    config_file,
    default_model,
    get_config,
    lang_dir,
    load_config,
    reload_config,
    rex_command,
    save_config,
    ui_language,
)


class TestPaths:
    def test_config_dir_env_override(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            assert str(config_dir()) == tmp

    def test_config_dir_xdg(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.delenv("STRELKA_CONFIG_DIR", raising=False)
            monkeypatch.setenv("XDG_CONFIG_HOME", tmp)
            assert config_dir() == Path(tmp) / "strelka"

    def test_config_dir_per_os(self, monkeypatch):
        monkeypatch.delenv("STRELKA_CONFIG_DIR", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        d = config_dir()
        assert d.name == "strelka"

    def test_config_file_name(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            assert config_file() == Path(tmp) / "strelka.toml"

    def test_lang_dir_env_override(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_LANG_DIR", tmp)
            assert lang_dir() == Path(tmp)

    def test_lang_dir_falls_back_to_layka_env(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.delenv("STRELKA_LANG_DIR", raising=False)
            monkeypatch.setenv("LAYKA_LANG_DIR", tmp)
            assert lang_dir() == Path(tmp)


class TestDefaults:
    def test_rex_defaults(self):
        cfg = RexConfig()
        assert cfg.command == ["python", "-m", "rex"]
        assert cfg.startup_timeout == 10.0
        assert cfg.restart_on_crash is True

    def test_ui_defaults(self):
        cfg = UIConfig()
        assert cfg.language == "en"
        assert cfg.theme == "auto"
        assert cfg.scrollback_limit == 10000

    def test_model_defaults(self):
        cfg = ModelConfig()
        assert cfg.model == "gpt-4o-mini"
        assert cfg.temperature == 0.7

    def test_logging_defaults(self):
        cfg = LoggingConfig()
        assert cfg.level == "INFO"
        assert cfg.file is None


class TestLoad:
    def test_load_defaults(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            cfg = load_config()
            assert isinstance(cfg, StrelkaConfig)
            assert cfg.rex.command == ["python", "-m", "rex"]
            assert cfg.ui.language == "en"
            assert cfg.model.model == "gpt-4o-mini"

    def test_load_from_file(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text(
                '[ui]\nlanguage = "bg"\ntheme = "dark"\n\n'
                '[model]\nmodel = "claude-3.5-sonnet"\ntemperature = 0.5\n'
            )
            cfg = load_config()
            assert cfg.ui.language == "bg"
            assert cfg.ui.theme == "dark"
            assert cfg.model.model == "claude-3.5-sonnet"
            assert cfg.model.temperature == 0.5
            # a default not mentioned in the file is preserved
            assert cfg.rex.command == ["python", "-m", "rex"]

    def test_file_value_wins_over_default(self, monkeypatch):
        """The core bug: a default must never overwrite a file value."""
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            # language "bg" set in file; every other UI key is left default.
            (Path(tmp) / "strelka.toml").write_text('[ui]\nlanguage = "bg"\n')
            cfg = load_config()
            assert cfg.ui.language == "bg"  # not reset to "en"
            assert cfg.ui.theme == "auto"  # untouched default

    def test_env_set_overrides_file(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text('[ui]\nlanguage = "fr"\n')
            monkeypatch.setenv("STRELKA_UI__LANGUAGE", "ru")
            cfg = load_config()
            assert cfg.ui.language == "ru"

    def test_unset_env_does_not_override_file(self, monkeypatch):
        """Only env vars actually set may override the file."""
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text(
                '[ui]\nlanguage = "bg"\ntheme = "dark"\n'
            )
            monkeypatch.setenv("STRELKA_UI__LANGUAGE", "de")  # only language set
            cfg = load_config()
            assert cfg.ui.language == "de"  # env wins where set
            assert cfg.ui.theme == "dark"  # file wins where env unset

    def test_env_list_json(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            monkeypatch.setenv("STRELKA_REX__COMMAND", '["python", "-m", "rex", "--debug"]')
            cfg = load_config()
            assert cfg.rex.command == ["python", "-m", "rex", "--debug"]

    def test_env_float(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            monkeypatch.setenv("STRELKA_MODEL__TEMPERATURE", "0.3")
            cfg = load_config()
            assert cfg.model.temperature == 0.3

    def test_bad_toml_falls_back(self, monkeypatch, caplog):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text("invalid toml [[[")
            with caplog.at_level(logging.WARNING):
                cfg = load_config()
            assert cfg.ui.language == "en"
            assert "Failed to parse" in caplog.text

    def test_out_of_range_value_falls_back(self, monkeypatch, caplog):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text('[model]\ntemperature = 3.0\n')
            with caplog.at_level(logging.WARNING):
                cfg = load_config()
            assert cfg.model.temperature == 0.7
            assert "validation failed" in caplog.text.lower()

    def test_bad_type_falls_back(self, monkeypatch, caplog):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text('[model]\ntemperature = "hot"\n')
            with caplog.at_level(logging.WARNING):
                cfg = load_config()
            assert cfg.model.temperature == 0.7

    def test_bad_enum_falls_back(self, monkeypatch, caplog):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text('[ui]\ntheme = "neon"\n')
            with caplog.at_level(logging.WARNING):
                cfg = load_config()
            assert cfg.ui.theme == "auto"

    def test_rex_as_bare_array(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            (Path(tmp) / "strelka.toml").write_text('rex = ["custom", "cmd"]\n')
            cfg = load_config()
            assert cfg.rex.command == ["custom", "cmd"]


class TestSave:
    def test_save_creates_file(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            save_config(StrelkaConfig(ui=UIConfig(language="bg")))
            content = (Path(tmp) / "strelka.toml").read_text()
            assert 'language = "bg"' in content

    def test_save_roundtrip(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            original = StrelkaConfig(
                ui=UIConfig(language="fr", theme="dark"),
                model=ModelConfig(model="test-model", temperature=0.9),
            )
            save_config(original)
            reloaded = load_config()
            assert reloaded.ui.language == "fr"
            assert reloaded.ui.theme == "dark"
            assert reloaded.model.model == "test-model"
            assert reloaded.model.temperature == 0.9

    def test_save_strips_secrets(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            cfg = StrelkaConfig()
            # inject a secret-looking entry into the rex env table
            cfg.rex.env = {"API_KEY": "sk-secret", "HOME": "/tmp"}
            save_config(cfg)
            content = (Path(tmp) / "strelka.toml").read_text()
            assert "sk-secret" not in content
            assert "api_key" not in content.lower()


class TestSingleton:
    def test_get_config_caches(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            reload_config()
            assert get_config() is get_config()

    def test_reload_new_instance(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            a = get_config()
            b = reload_config()
            assert a is not b

    def test_reload_picks_up_changes(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            assert reload_config().ui.language == "en"
            (Path(tmp) / "strelka.toml").write_text('[ui]\nlanguage = "de"\n')
            assert reload_config().ui.language == "de"


class TestConvenience:
    def test_getters(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("STRELKA_CONFIG_DIR", tmp)
            _clear_env(monkeypatch)
            reload_config()
            assert rex_command() == ["python", "-m", "rex"]
            assert ui_language() == "en"
            assert default_model() == "gpt-4o-mini"


def test_no_import_time_logging_config():
    """Importing the module must not call logging.basicConfig."""
    import importlib

    import strelka.config as mod

    root_before = len(logging.getLogger().handlers)
    importlib.reload(mod)
    assert len(logging.getLogger().handlers) == root_before


def _clear_env(monkeypatch) -> None:
    """Remove any STRELKA_ env overrides inherited from the real environment."""
    import os

    for name in list(os.environ):
        if name.startswith("STRELKA_") and name != "STRELKA_CONFIG_DIR":
            monkeypatch.delenv(name, raising=False)
