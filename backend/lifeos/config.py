from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = Path("~/Library/Application Support/LifeOS").expanduser()


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path
    database_path: Path
    uploads_dir: Path
    backups_dir: Path
    logs_dir: Path
    api_key: str = Field(min_length=32)
    session_secret: str = Field(min_length=32)
    ai_enabled: bool = False
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "deepseek-r1:7b"
    ollama_timeout_seconds: int = 20
    backup_daily_retention: int = 30
    backup_monthly_retention: int = 12
    max_upload_bytes: int = 20 * 1024 * 1024
    project_root: Path = PROJECT_ROOT


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.lower() in {"1", "true", "yes", "on"}


def _int(value: str | int | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _write_generated_env(path: Path, api_key: str, session_secret: str) -> None:
    existing = _read_env_file(path)
    existing.setdefault("LIFE_OS_API_KEY", api_key)
    existing.setdefault("LIFE_OS_SESSION_SECRET", session_secret)
    lines = [
        "# Generated locally by Life OS. Do not commit or share this file.",
        f"LIFE_OS_API_KEY={existing['LIFE_OS_API_KEY']}",
        f"LIFE_OS_SESSION_SECRET={existing['LIFE_OS_SESSION_SECRET']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.getenv("LIFE_OS_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    data_dir.chmod(0o700)
    env_path = data_dir / ".env"
    file_values = _read_env_file(env_path)

    def value(name: str, default: str | None = None) -> str | None:
        return os.getenv(name, file_values.get(name, default))

    api_key = value("LIFE_OS_API_KEY") or secrets.token_urlsafe(48)
    session_secret = value("LIFE_OS_SESSION_SECRET") or secrets.token_urlsafe(48)
    if (
        not env_path.exists()
        or not file_values.get("LIFE_OS_API_KEY")
        or not file_values.get("LIFE_OS_SESSION_SECRET")
    ):
        _write_generated_env(env_path, api_key, session_secret)

    uploads_dir = data_dir / "uploads"
    backups_dir = data_dir / "backups"
    logs_dir = data_dir / "logs"
    for directory in (uploads_dir, backups_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)

    return Settings(
        host=value("LIFE_OS_HOST", "127.0.0.1") or "127.0.0.1",
        port=_int(value("LIFE_OS_PORT"), 8765),
        data_dir=data_dir,
        database_path=data_dir / "lifeos.db",
        uploads_dir=uploads_dir,
        backups_dir=backups_dir,
        logs_dir=logs_dir,
        api_key=api_key,
        session_secret=session_secret,
        ai_enabled=_bool(value("LIFE_OS_AI_ENABLED"), False),
        ollama_url=value("LIFE_OS_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
        or "http://127.0.0.1:11434/api/generate",
        ollama_model=value("LIFE_OS_OLLAMA_MODEL", "deepseek-r1:7b") or "deepseek-r1:7b",
        ollama_timeout_seconds=_int(value("LIFE_OS_OLLAMA_TIMEOUT_SECONDS"), 20),
        backup_daily_retention=_int(value("LIFE_OS_BACKUP_DAILY_RETENTION"), 30),
        backup_monthly_retention=_int(value("LIFE_OS_BACKUP_MONTHLY_RETENTION"), 12),
    )
