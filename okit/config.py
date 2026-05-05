"""okit user config — provider selection lives here.

Stored at ``~/.config/okit/config.json`` (or ``$XDG_CONFIG_HOME/okit/...``).
On first contact, ``ensure_initialized`` writes a default config that enables
every provider whose CLI binary is detected on PATH. If nothing is detected,
all known providers are enabled — better to fail loudly when installing than
to silently install nothing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from okit.providers import ALL_PROVIDERS, PROVIDERS_BY_ID, Provider

CONFIG_VERSION = 1


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "okit"


def config_path() -> Path:
    """Allow ``OKIT_CONFIG`` env override (mirrors OKIT_MANIFEST pattern)."""
    env_path = os.environ.get("OKIT_CONFIG", "")
    if env_path:
        return Path(env_path)
    return config_dir() / "config.json"


@dataclass
class Config:
    """In-memory view of okit's user config."""

    enabled_providers: list[str] = field(default_factory=list)
    version: int = CONFIG_VERSION

    def is_enabled(self, provider_id: str) -> bool:
        return provider_id in self.enabled_providers

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "providers": {"enabled": list(self.enabled_providers)},
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Config":
        providers = raw.get("providers", {}) or {}
        enabled = providers.get("enabled", []) or []
        # Defensive: drop unknown ids so a stale config can't crash later runs.
        enabled = [pid for pid in enabled if pid in PROVIDERS_BY_ID]
        return cls(
            enabled_providers=enabled,
            version=int(raw.get("version", CONFIG_VERSION)),
        )


# --- I/O ---


def load() -> Config:
    """Load config from disk, or return an empty Config if absent."""
    path = config_path()
    if not path.exists():
        return Config()
    try:
        return Config.from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        # Corrupt config shouldn't brick the CLI — fall back to defaults.
        return Config()


def save(config: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2) + "\n")


# --- First-run initialization ---


def _autodetect_enabled_providers() -> list[str]:
    """Return ids of providers whose CLI binary is on PATH.

    Falls back to every known provider when nothing is detected so that a
    user without any tools installed yet still has a usable config.
    """
    detected = [p.id for p in ALL_PROVIDERS if p.is_available()]
    if detected:
        return detected
    return [p.id for p in ALL_PROVIDERS]


def ensure_initialized() -> Config:
    """Create the config on first run, then return the active config.

    Idempotent — safe to call from every CLI entry point.
    """
    path = config_path()
    if path.exists():
        return load()

    config = Config(enabled_providers=_autodetect_enabled_providers())
    save(config)
    return config


# --- Convenience ---


def enabled_providers(config: Config | None = None) -> list[Provider]:
    """Return the active Provider instances in registration order."""
    cfg = config if config is not None else load()
    return [PROVIDERS_BY_ID[pid] for pid in cfg.enabled_providers if pid in PROVIDERS_BY_ID]
