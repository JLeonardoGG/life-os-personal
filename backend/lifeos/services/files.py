from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from lifeos.config import Settings
from lifeos.models import UploadedFile


def safe_filename(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip(".-")
    return clean[:180] or "archivo"


def store_uploaded_bytes(
    db: Session,
    settings: Settings,
    content: bytes,
    original_name: str,
    content_type: str,
    purpose: str,
    metadata: dict | None = None,
) -> tuple[UploadedFile, bool]:
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(UploadedFile).where(UploadedFile.sha256 == digest))
    if existing:
        return existing, False

    date_folder = datetime.now().strftime("%Y/%m")
    target_dir = settings.uploads_dir / purpose / date_folder
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{digest[:16]}-{safe_filename(original_name)}"
    target = target_dir / stored_name
    target.write_bytes(content)
    target.chmod(0o600)

    record = UploadedFile(
        original_name=Path(original_name).name,
        stored_name=stored_name,
        relative_path=str(target.relative_to(settings.data_dir)),
        content_type=content_type or "application/octet-stream",
        size_bytes=len(content),
        sha256=digest,
        purpose=purpose,
        details=metadata or {},
    )
    db.add(record)
    db.flush()
    return record, True
