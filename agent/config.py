"""Configuration management for speckit-enhanced."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "agent_config.yaml"

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager with YAML file and environment variable support."""

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self):
        """Load configuration from YAML file and overlay environment variables."""
        # Load defaults from YAML
        if self._config_path.exists():
            try:
                with open(self._config_path, "r") as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info("Loaded configuration from %s", self._config_path)
            except Exception as e:
                logger.warning("Failed to load config file: %s", e)
                self._config = {}
        else:
            logger.warning("Config file not found at %s, using defaults", self._config_path)
            self._config = {}

        # Overlay environment variables (env vars take precedence)
        self._apply_env_overrides()

    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        # LLM configuration
        self.set("llm.claude.model", os.getenv("CLAUDE_MODEL", self.get("llm.claude.model", "claude-opus-4-8")))
        self.set("llm.openai.model", os.getenv("OPENAI_MODEL", self.get("llm.openai.model", "gpt-4o")))
        self.set("llm.ollama.model", os.getenv("OLLAMA_MODEL", self.get("llm.ollama.model", "llama3")))
        self.set("llm.ollama.base_url", os.getenv("OLLAMA_BASE_URL", self.get("llm.ollama.base_url", "http://localhost:11434")))

        # Privacy mode
        privacy_mode = os.getenv("PRIVACY_MODE", "false").lower() == "true"
        self.set("llm.privacy_mode", privacy_mode)

        # Server configuration
        self.set("server.host", os.getenv("HOST", self.get("server.host", "0.0.0.0")))
        self.set("server.port", int(os.getenv("PORT", self.get("server.port", 8020))))

        # Paths
        self.set("agent.data_dir", os.getenv("DATA_DIR", self.get("agent.data_dir", "./data")))
        self.set("agent.models_dir", os.getenv("MODELS_DIR", self.get("agent.models_dir", "./models")))

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-notation key."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any):
        """Set a configuration value by dot-notation key."""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def get_all(self) -> Dict[str, Any]:
        """Get the entire configuration dictionary."""
        return self._config.copy()

    def reload(self):
        """Reload configuration from file."""
        self._load_config()
        logger.info("Configuration reloaded")


# Global config instance
_config: Config = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config_path(path: Path):
    """Set a custom configuration file path and reload."""
    global _config
    _config = Config(path)
