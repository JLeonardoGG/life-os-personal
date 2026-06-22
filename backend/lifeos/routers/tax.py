from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifeos.config import Settings, get_settings
from lifeos.database import get_db
from lifeos.models import TaxDocument
from lifeos.security import require_session_or_api_key
from lifeos.serializers import from_cents, model_dict
from lifeos.services.files import store_uploaded_bytes
from lifeos.services.tax_parser import TaxXmlError, parse_tax_xml

router = APIRouter(
    prefix="/api/tax",
    tags=["tax"],
    dependencies=[Depends(require_session_or_api_key)],
)


@router.post("/upload-xml")
async def upload_tax_xml(
    files: list[UploadFile] = File(...),
    kind: str = Form("auto"),
    taxpayer_rfc: str = Form(""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if kind not in {"auto", "income", "expense", "retention"}:
        raise HTTPException(status_code=400, detail="Invalid document kind")
    result = {"imported": [], "duplicates": [], "errors": []}
    for upload in files:
        try:
            content = await upload.read(settings.max_upload_bytes + 1)
            if len(content) > settings.max_upload_bytes:
                raise TaxXmlError("Archivo excede el limite permitido")
            if not upload.filename or not upload.filename.lower().endswith(".xml"):
                raise TaxXmlError("Solo se permiten archivos XML")
            parsed = parse_tax_xml(content, kind, taxpayer_rfc)
            existing = db.scalar(
                select(TaxDocument).where(
                    (TaxDocument.source_hash == parsed["source_hash"])
                    | (TaxDocument.uuid.is_not(None) & (TaxDocument.uuid == parsed["uuid"]))
                )
            )
            if existing:
                result["duplicates"].append(upload.filename)
                continue
            stored_file, _ = store_uploaded_bytes(
                db,
                settings,
                content,
                upload.filename,
                upload.content_type or "application/xml",
                "tax",
                {"period": parsed["period"], "kind": parsed["document_kind"]},
            )
            document = TaxDocument(**parsed, file_id=stored_file.id)
            db.add(document)
            db.flush()
            result["imported"].append(model_dict(document))
        except TaxXmlError as exc:
            result["errors"].append({"file": upload.filename, "error": str(exc)})
        finally:
            await upload.close()
    db.commit()
    return result


def _tax_summary(db: Session, periods: list[str]) -> dict:
    documents = db.scalars(
        select(TaxDocument).where(
            TaxDocument.deleted_at.is_(None),
            TaxDocument.period.in_(periods),
        )
    ).all()
    income_docs = [item for item in documents if item.document_kind == "income"]
    expense_docs = [item for item in documents if item.document_kind == "expense"]
    retention_docs = [item for item in documents if item.document_kind == "retention"]
    income = sum(item.subtotal_cents for item in income_docs)
    expenses = sum(item.subtotal_cents for item in expense_docs)
    iva_transferred = sum(item.tax_transferred_cents for item in income_docs)
    iva_creditable = sum(item.tax_transferred_cents for item in expense_docs)
    iva_withheld = sum(
        int((item.summary or {}).get("iva_withheld", 0) * 100) for item in income_docs + retention_docs
    )
    isr_withheld = sum(
        int((item.summary or {}).get("isr_withheld", 0) * 100) for item in income_docs + retention_docs
    )
    return {
        "periods": periods,
        "document_count": len(documents),
        "income": from_cents(income),
        "deductible_expenses": from_cents(expenses),
        "estimated_profit": from_cents(income - expenses),
        "iva_transferred": from_cents(iva_transferred),
        "iva_creditable": from_cents(iva_creditable),
        "iva_withheld": from_cents(iva_withheld),
        "isr_withheld": from_cents(isr_withheld),
        "estimated_iva_balance": from_cents(iva_transferred - iva_creditable - iva_withheld),
        "notice": "Estimacion informativa; valida los importes en SAT o con tu contador.",
    }


@router.get("/monthly-summary")
def monthly_summary(period: str | None = None, db: Session = Depends(get_db)) -> dict:
    selected = period or datetime.now().strftime("%Y-%m")
    if len(selected) != 7:
        raise HTTPException(status_code=400, detail="period must use YYYY-MM")
    return _tax_summary(db, [selected])


@router.get("/annual-summary")
def annual_summary(year: int | None = None, db: Session = Depends(get_db)) -> dict:
    selected = year or datetime.now().year
    periods = [f"{selected}-{month:02d}" for month in range(1, 13)]
    result = _tax_summary(db, periods)
    result["year"] = selected
    result["months"] = {
        period: _tax_summary(db, [period])
        for period in periods
        if db.scalar(select(func.count()).select_from(TaxDocument).where(TaxDocument.period == period))
    }
    return result
