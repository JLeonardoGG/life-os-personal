from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lifeos import __version__
from lifeos.config import Settings
from lifeos.models import (
    AcademicCourse,
    Account,
    AppSetting,
    AutomationLog,
    Budget,
    CarLog,
    CarReminder,
    DailyReview,
    Debt,
    DebtMovement,
    Event,
    HealthLog,
    ImportBatch,
    InboxMessage,
    Investment,
    MonthlyClosure,
    Note,
    Project,
    Routine,
    Subscription,
    Task,
    TaxDocument,
    TaxEntry,
    Transaction,
    UploadedFile,
)
from lifeos.serializers import model_dict

BACKUP_MODELS = [
    Account,
    Transaction,
    Budget,
    MonthlyClosure,
    Subscription,
    Investment,
    Debt,
    DebtMovement,
    TaxDocument,
    TaxEntry,
    Task,
    Event,
    Routine,
    HealthLog,
    CarLog,
    CarReminder,
    Note,
    DailyReview,
    AcademicCourse,
    Project,
    UploadedFile,
    ImportBatch,
    InboxMessage,
    AutomationLog,
    AppSetting,
]


def build_export_payload(db: Session) -> dict[str, Any]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for model in BACKUP_MODELS:
        records = db.scalars(select(model)).all()
        tables[model.__tablename__] = [model_dict(record) for record in records]
    return {
        "app": "LifeOS",
        "schema_version": 1,
        "app_version": __version__,
        "exported_at": datetime.now(UTC).isoformat(),
        "contains_credentials": False,
        "tables": tables,
    }


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8")


def _copy_sqlite(source: Path, target: Path) -> None:
    source_connection = sqlite3.connect(source)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


def _prune_backups(settings: Settings) -> None:
    database_files = sorted(settings.backups_dir.glob("lifeos-*.db"), reverse=True)
    daily: dict[str, Path] = {}
    monthly: dict[str, Path] = {}
    for path in database_files:
        stamp = path.stem.removeprefix("lifeos-")
        day = stamp[:10]
        month = stamp[:7]
        daily.setdefault(day, path)
        monthly.setdefault(month, path)
    keep = set(list(daily.values())[: settings.backup_daily_retention])
    keep.update(list(monthly.values())[: settings.backup_monthly_retention])
    for database_path in database_files:
        if database_path in keep:
            continue
        stem = database_path.stem
        for path in settings.backups_dir.glob(f"{stem}.*"):
            path.unlink(missing_ok=True)


def create_backup(db: Session, settings: Settings, reason: str = "manual") -> dict[str, Any]:
    now = datetime.now(UTC)
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    stem = f"lifeos-{stamp}"
    database_path = settings.backups_dir / f"{stem}.db"
    json_path = settings.backups_dir / f"{stem}.json"
    manifest_path = settings.backups_dir / f"{stem}.manifest.json"

    payload = build_export_payload(db)
    json_content = _json_bytes(payload)
    json_path.write_bytes(json_content)
    json_path.chmod(0o600)
    _copy_sqlite(settings.database_path, database_path)
    database_path.chmod(0o600)

    manifest = {
        "created_at": now.isoformat(),
        "reason": reason,
        "database": database_path.name,
        "database_sha256": hashlib.sha256(database_path.read_bytes()).hexdigest(),
        "json": json_path.name,
        "json_sha256": hashlib.sha256(json_content).hexdigest(),
        "contains_credentials": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    _prune_backups(settings)
    return manifest


def ensure_daily_backup(db: Session, settings: Settings) -> dict[str, Any] | None:
    today_prefix = f"lifeos-{datetime.now(UTC).strftime('%Y-%m-%d')}"
    if any(settings.backups_dir.glob(f"{today_prefix}*.db")):
        return None
    return create_backup(db, settings, reason="daily-startup")
