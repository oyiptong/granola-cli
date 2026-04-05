from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_API_BASE_URL = "https://public-api.granola.ai"


@dataclass(frozen=True)
class AppConfig:
    api_base_url: str
    db_path: str


def default_config() -> AppConfig:
    return AppConfig(api_base_url=DEFAULT_API_BASE_URL, db_path=str(default_db_path()))


def default_config_path() -> Path:
    return Path("~/.config/granola/config.toml").expanduser()


def default_db_path() -> Path:
    return Path("~/.local/share/granola-cli/granola-cli.sqlite3").expanduser()


def load_or_create_config(config_path: Path | None = None) -> AppConfig:
    path = (config_path or default_config_path()).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        config = default_config()
        write_config(config, path)
        return config

    with path.open("rb") as handle:
        data = tomllib.load(handle)

    config = AppConfig(
        api_base_url=str(data.get("api_base_url", DEFAULT_API_BASE_URL)),
        db_path=str(data.get("db_path", str(default_db_path()))),
    )
    write_config(config, path)
    return config


def write_config(config: AppConfig, config_path: Path | None = None) -> None:
    path = (config_path or default_config_path()).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize_config(config), encoding="utf-8")


def _serialize_config(config: AppConfig) -> str:
    return (
        f'api_base_url = "{_toml_escape(config.api_base_url)}"\n'
        f'db_path = "{_toml_escape(config.db_path)}"\n'
    )


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
