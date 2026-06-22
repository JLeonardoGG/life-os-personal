from __future__ import annotations

import json
from pathlib import Path


def test_health_is_public_and_finance_requires_session(app_context):
    client, _settings = app_context
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/transactions").status_code == 401


def test_transaction_crud_and_summary(client):
    payload = {
        "date": "2026-06-21",
        "type": "gasto",
        "category": "Transporte",
        "name": "Gasolina demo",
        "amount": 180.5,
    }
    created = client.post("/api/transactions", json=payload)
    assert created.status_code == 201
    record = created.json()
    assert record["amount"] == 180.5

    updated = client.put(
        f"/api/transactions/{record['id']}",
        json={"amount": 200, "category": "Auto"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 200

    listed = client.get("/api/transactions")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    summary = client.get("/api/summary/month")
    assert summary.status_code == 200
    assert "finance" in summary.json()

    deleted = client.delete(f"/api/transactions/{record['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/transactions").json()["total"] == 0


def test_inbox_is_api_key_protected_idempotent_and_confirmable(app_context):
    client, settings = app_context
    payload = {
        "source": "n8n",
        "message": "Gasté $180 en gasolina",
        "timestamp": "2026-06-21T22:30:00-06:00",
        "external_id": "demo-1",
        "metadata": {},
    }
    assert client.post("/api/inbox/message", json=payload).status_code == 401
    headers = {
        "X-LifeOS-API-Key": settings.api_key,
        "Idempotency-Key": "demo-inbox-1",
    }
    first = client.post("/api/inbox/message", json=payload, headers=headers)
    second = client.post("/api/inbox/message", json=payload, headers=headers)
    assert first.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["proposed_type"] == "expense"

    confirm = client.post(
        f"/api/inbox/messages/{first.json()['id']}/confirm",
        headers={
            "X-LifeOS-API-Key": settings.api_key,
            "Idempotency-Key": "demo-confirm-1",
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "confirmed"

    transactions = client.get(
        "/api/transactions",
        headers={"X-LifeOS-API-Key": settings.api_key},
    )
    assert transactions.json()["total"] == 1
    logs = client.get(
        "/api/automation/logs",
        headers={"X-LifeOS-API-Key": settings.api_key},
    )
    assert logs.json()["total"] == 2


def test_legacy_import_is_previewed_idempotent_and_excludes_credentials(client):
    fixture = Path(__file__).parent / "fixtures" / "legacy_backup_demo.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    preview = client.post("/api/import/localstorage?mode=preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["counts"]["transactions"] == 1
    assert preview.json()["excluded"]["credentials"] == 1

    first = client.post("/api/import/localstorage?mode=commit", json=payload)
    second = client.post("/api/import/localstorage?mode=commit", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "committed"
    assert second.json()["status"] == "already_imported"
    assert client.get("/api/transactions").json()["total"] == 1
    assert client.get("/api/tasks").json()["total"] == 1

    exported = client.get("/api/export/backup")
    assert exported.status_code == 200
    assert exported.json()["contains_credentials"] is False
    exported_text = json.dumps(exported.json())
    assert "CREDENCIAL LEGADA EXCLUIDA" not in exported_text
    snapshot = next(
        item
        for item in exported.json()["tables"]["app_settings"]
        if item["key"] == "legacy_snapshot_latest"
    )
    assert "credentials" not in snapshot["value"]["state"]


def test_tax_xml_upload_and_summary(client):
    fixture = Path(__file__).parent / "fixtures" / "demo_cfdi.xml"
    with fixture.open("rb") as handle:
        response = client.post(
            "/api/tax/upload-xml",
            data={"kind": "income", "taxpayer_rfc": "XAXX010101000"},
            files=[("files", ("demo_cfdi.xml", handle, "application/xml"))],
        )
    assert response.status_code == 200
    assert len(response.json()["imported"]) == 1
    summary = client.get("/api/tax/monthly-summary?period=2026-06")
    assert summary.status_code == 200
    assert summary.json()["income"] == 100
    assert summary.json()["iva_transferred"] == 16


def test_manual_backup_creates_sqlite_json_and_manifest(client, settings):
    response = client.post("/api/backup/create?reason=test")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["contains_credentials"] is False
    assert (settings.backups_dir / manifest["database"]).exists()
    assert (settings.backups_dir / manifest["json"]).exists()
