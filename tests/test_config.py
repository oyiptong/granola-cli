from pathlib import Path

from granola.config import AppConfig, DEFAULT_API_BASE_URL, default_db_path, load_or_create_config, write_config


def test_load_or_create_config_writes_defaults(tmp_path) -> None:
    path = tmp_path / "config.toml"
    config = load_or_create_config(path)
    assert config.api_base_url == DEFAULT_API_BASE_URL
    assert config.db_path == str(default_db_path())
    assert path.exists()


def test_load_or_create_config_reads_existing_values(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('api_base_url = "http://localhost:9999"\ndb_path = "/tmp/custom.sqlite3"\n', encoding="utf-8")
    config = load_or_create_config(path)
    assert config == AppConfig(api_base_url="http://localhost:9999", db_path="/tmp/custom.sqlite3")


def test_write_config_serializes_toml(tmp_path) -> None:
    path = tmp_path / "config.toml"
    write_config(AppConfig(api_base_url="http://example.test", db_path=str(tmp_path / "db.sqlite3")), path)
    contents = path.read_text(encoding="utf-8")
    assert 'api_base_url = "http://example.test"' in contents
    assert f'db_path = "{tmp_path / "db.sqlite3"}"' in contents
