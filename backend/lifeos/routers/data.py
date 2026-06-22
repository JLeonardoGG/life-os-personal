from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from lifeos.config import Settings, get_settings
from lifeos.database import get_db
from lifeos.security import require_session_or_api_key
from lifeos.services.backups import build_export_payload, create_backup
from lifeos.services.legacy_import import commit_legacy_import, preview_legacy_import

router = APIRouter(
    prefix="/api",
    tags=["data"],
    dependencies=[Depends(require_session_or_api_key)],
)


@router.get("/export/backup")
def export_backup(db: Session = Depends(get_db)) -> Response:
    payload = build_export_payload(db)
    filename = f"lifeos-v1-backup-{datetime.now().strftime('%Y-%m-%d')}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/backup/create")
def backup_create(
    reason: str = "manual",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return create_backup(db, settings, reason=reason[:80])


@router.post("/import/localstorage")
def import_localstorage(
    payload: dict = Body(...),
    mode: str = Query("preview", pattern="^(preview|commit)$"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not isinstance(payload.get("state", payload), dict):
        raise HTTPException(status_code=400, detail="Invalid Life OS payload")
    if mode == "preview":
        return preview_legacy_import(payload)
    create_backup(db, settings, reason="before-legacy-import")
    try:
        return commit_legacy_import(db, settings, payload)
    except Exception:
        db.rollback()
        raise
