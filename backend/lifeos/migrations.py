from __future__ import annotations

from alembic import command
from alembic.config import Config

from lifeos.config import Settings


def upgrade_database(settings: Settings) -> None:
    config = Config(str(settings.project_root / "alembic.ini"))
    config.set_main_option("script_location", str(settings.project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{settings.database_path}")
    command.upgrade(config, "head")
    settings.database_path.chmod(0o600)
