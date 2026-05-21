import pytest
import os
from src.common.config import Config

class TestConfig:
    def test_load_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"app": {"name": "test", "port": 8080}}')
        config = Config(str(config_file))
        assert config.get("app.name") == "test"
        assert config.get("app.port") == 8080

    def test_default_value(self):
        config = Config()
        assert config.get("nonexistent.key", "default") == "default"

    def test_set_value(self):
        config = Config()
        config.set("database.host", "localhost")
        assert config.get("database.host") == "localhost"

    def test_nested_set(self):
        config = Config()
        config.set("a.b.c.d", "value")
        assert config.get("a.b.c.d") == "value"

    def test_to_dict(self):
        config = Config()
        config.set("key1", "value1")
        config.set("key2", "value2")
        data = config.to_dict()
        assert data["key1"] == "value1"
        assert data["key2"] == "value2"

    def test_env_bool_true_coerced(self, monkeypatch):
        """AO_FEATURE_ENABLED=true should yield boolean True."""
        monkeypatch.setenv("AO_FEATURE_ENABLED", "true")
        config = Config()
        assert config.get("feature.enabled") is True

    def test_env_bool_false_coerced(self, monkeypatch):
        """AO_FEATURE_ENABLED=false should yield boolean False (not truthy string)."""
        monkeypatch.setenv("AO_FEATURE_ENABLED", "false")
        config = Config()
        assert config.get("feature.enabled") is False

    def test_env_bool_yes_no(self, monkeypatch):
        """AO_FLAG=yes -> True, AO_FLAG2=no -> False."""
        monkeypatch.setenv("AO_FLAG", "yes")
        monkeypatch.setenv("AO_FLAG2", "no")
        config = Config()
        assert config.get("flag") is True
        assert config.get("flag2") is False

    def test_env_bool_one_zero(self, monkeypatch):
        """AO_ENABLED=1 -> True, AO_DISABLED=0 -> False."""
        monkeypatch.setenv("AO_ENABLED", "1")
        monkeypatch.setenv("AO_DISABLED", "0")
        config = Config()
        assert config.get("enabled") is True
        assert config.get("disabled") is False

    def test_env_int_coerced(self, monkeypatch):
        """AO_PORT=8080 should yield integer 8080."""
        monkeypatch.setenv("AO_PORT", "8080")
        config = Config()
        assert config.get("port") == 8080
        assert isinstance(config.get("port"), int)

    def test_env_str_unchanged(self, monkeypatch):
        """Non-boolean/non-numeric strings stay as strings."""
        monkeypatch.setenv("AO_APP_NAME", "my-agent")
        config = Config()
        assert config.get("app.name") == "my-agent"
        assert isinstance(config.get("app.name"), str)
