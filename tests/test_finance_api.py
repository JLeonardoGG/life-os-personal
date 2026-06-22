from __future__ import annotations

from datetime import date

from lifeos.models import Transaction


def transaction_payload(**overrides):
    payload = {
        "date": "2026-06-22",
        "type": "expense",
        "category": "Transporte",
        "name": "Gasolina demo",
        "description": "Carga de prueba",
        "amount": 180.55,
        "expense_nature": "corriente",
        "source": "frontend",
        "metadata": {"fixture": True},
    }
    payload.update(overrides)
    return payload


def test_transaction_create_requires_and_honors_idempotency_key(client):
    payload = transaction_payload()
    assert client.post("/api/transactions", json=payload).status_code == 400

    headers = {"Idempotency-Key": "finance-create-1"}
    first = client.post("/api/transactions", json=payload, headers=headers)
    second = client.post(
        "/api/transactions",
        json=transaction_payload(amount=999.99, name="Payload repetido"),
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["amount"] == 180.55
    assert second.json()["type"] == "gasto"
    assert client.get("/api/transactions").json()["total"] == 1


def test_transaction_update_soft_delete_restore_and_history(client):
    created = client.post(
        "/api/transactions",
        json=transaction_payload(type="income", amount=123.45),
        headers={"Idempotency-Key": "finance-lifecycle-1"},
    )
    assert created.status_code == 201
    record = created.json()

    updated = client.put(
        f"/api/transactions/{record['id']}",
        json={"amount": 200.25, "category": "Negocio", "description": "Actualizado"},
        headers={"Idempotency-Key": "finance-update-1"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 200.25
    assert updated.json()["category"] == "Negocio"
    assert updated.json()["updated_at"] >= record["updated_at"]

    deleted = client.delete(
        f"/api/transactions/{record['id']}",
        headers={"Idempotency-Key": "finance-delete-1"},
    )
    assert deleted.status_code == 204
    assert client.delete(f"/api/transactions/{record['id']}").status_code == 204
    assert client.get("/api/transactions").json()["total"] == 0

    restored = client.post(
        f"/api/transactions/{record['id']}/restore",
        headers={"Idempotency-Key": "finance-restore-1"},
    )
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert client.get("/api/transactions").json()["total"] == 1

    history = client.get(f"/api/transactions/{record['id']}/history")
    assert history.status_code == 200
    assert {item["action"] for item in history.json()["items"]} == {
        "create",
        "update",
        "delete",
        "restore",
    }


def test_transaction_validation_and_account_reference(client):
    invalid_amount = client.post(
        "/api/transactions",
        json=transaction_payload(amount=-1),
        headers={"Idempotency-Key": "finance-invalid-amount"},
    )
    assert invalid_amount.status_code == 422

    excessive_precision = client.post(
        "/api/transactions",
        json=transaction_payload(amount=10.123),
        headers={"Idempotency-Key": "finance-invalid-precision"},
    )
    assert excessive_precision.status_code == 422

    invalid_account = client.post(
        "/api/transactions",
        json=transaction_payload(account_id="00000000-0000-0000-0000-000000000000"),
        headers={"Idempotency-Key": "finance-invalid-account"},
    )
    assert invalid_account.status_code == 422

    account = client.post(
        "/api/accounts",
        json={
            "name": "Cuenta demo",
            "institution": "Banco demo",
            "account_type": "debit",
        },
    )
    assert account.status_code == 201
    valid = client.post(
        "/api/transactions",
        json=transaction_payload(account_id=account.json()["id"], amount=10.01),
        headers={"Idempotency-Key": "finance-valid-account"},
    )
    assert valid.status_code == 201
    assert valid.json()["amount"] == 10.01
    assert valid.json()["account_id"] == account.json()["id"]


def test_budget_crud_uses_pesos_and_soft_delete(client):
    created = client.post(
        "/api/budgets",
        json={
            "period": "2026-07",
            "income_target": 35000.25,
            "expense_limit": 12000.5,
            "savings_target": 20000,
            "category_limits": {"Comida": 2500.75},
        },
    )
    assert created.status_code == 200
    budget = created.json()
    assert budget["income_target"] == 35000.25
    assert budget["category_limits"]["Comida"] == 2500.75

    updated = client.put(
        f"/api/budgets/{budget['id']}",
        json={"expense_limit": 11000.25, "category_limits": {"Comida": 2000}},
    )
    assert updated.status_code == 200
    assert updated.json()["expense_limit"] == 11000.25
    assert updated.json()["category_limits"]["Comida"] == 2000

    invalid = client.post(
        "/api/budgets",
        json={"period": "2026-08", "category_limits": {"Ocio": -1}},
    )
    assert invalid.status_code == 422

    assert client.delete(f"/api/budgets/{budget['id']}").status_code == 204
    assert client.get("/api/budgets").json()["total"] == 0

    restored = client.post(
        "/api/budgets",
        json={"period": "2026-07", "income_target": 36000},
    )
    assert restored.status_code == 200
    assert restored.json()["id"] == budget["id"]
    assert client.get("/api/budgets").json()["total"] == 1


def test_subscription_crud_and_next_due_date(client):
    created = client.post(
        "/api/subscriptions",
        json={
            "name": "Internet demo",
            "amount": 599.9,
            "category": "Servicios",
            "billing_day": 31,
            "frequency": "monthly",
            "payment_method": "Tarjeta demo",
            "active": True,
        },
    )
    assert created.status_code == 201
    subscription = created.json()
    assert subscription["amount"] == 599.9
    assert subscription["next_due_date"]

    updated = client.put(
        f"/api/subscriptions/{subscription['id']}",
        json={"amount": 649.5, "active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 649.5
    assert updated.json()["active"] is False

    assert client.delete(f"/api/subscriptions/{subscription['id']}").status_code == 204
    assert client.get("/api/subscriptions").json()["total"] == 0


def test_debt_crud_movements_balance_and_soft_delete(client):
    created = client.post(
        "/api/debts",
        json={
            "entity": "Tarjeta demo",
            "direction": "owed",
            "amount": 10000,
            "minimum_payment": 750.25,
            "institution": "Banco demo",
            "debt_type": "credit_card",
            "interest_rate": 42.5,
            "due_date": "2026-07-15",
        },
    )
    assert created.status_code == 201
    debt = created.json()
    assert debt["initial_amount"] == 10000
    assert debt["amount"] == 10000
    assert debt["minimum_payment"] == 750.25
    assert debt["interest_rate"] == 42.5

    payment = client.post(
        f"/api/debts/{debt['id']}/movements",
        json={
            "date": "2026-06-22",
            "kind": "debt_payment",
            "amount": 1000.5,
            "description": "Pago demo",
        },
    )
    assert payment.status_code == 201
    assert payment.json()["amount"] == 1000.5

    charge = client.post(
        f"/api/debts/{debt['id']}/movements",
        json={
            "date": "2026-06-23",
            "kind": "interest",
            "amount": 100,
            "description": "Interés demo",
        },
    )
    assert charge.status_code == 201
    listed = client.get("/api/debts").json()
    assert listed["items"][0]["amount"] == 9099.5

    movements = client.get(f"/api/debts/{debt['id']}/movements?limit=1")
    assert movements.status_code == 200
    assert movements.json()["total"] == 2
    assert len(movements.json()["items"]) == 1
    interest_movement = movements.json()["items"][0]
    assert interest_movement["kind"] == "interest"
    assert client.delete(
        f"/api/debts/{debt['id']}/movements/{interest_movement['id']}"
    ).status_code == 204
    assert client.get("/api/debts").json()["items"][0]["amount"] == 8999.5
    assert client.get(f"/api/debts/{debt['id']}/movements").json()["total"] == 1

    updated = client.put(
        f"/api/debts/{debt['id']}",
        json={"minimum_payment": 800, "status": "restructured"},
    )
    assert updated.status_code == 200
    assert updated.json()["minimum_payment"] == 800
    assert updated.json()["status"] == "restructured"

    assert client.delete(f"/api/debts/{debt['id']}").status_code == 204
    assert client.get("/api/debts").json()["total"] == 0
    assert client.get(f"/api/debts/{debt['id']}/movements").status_code == 404


def test_debt_rejects_invalid_movement_kind(client):
    debt = client.post(
        "/api/debts",
        json={"entity": "Demo", "direction": "owed", "amount": 0},
    ).json()
    response = client.post(
        f"/api/debts/{debt['id']}/movements",
        json={
            "date": "2026-06-22",
            "kind": "unknown",
            "amount": 10,
        },
    )
    assert response.status_code == 422


def test_investment_crud_uses_pesos_and_soft_delete(client):
    created = client.post(
        "/api/investments",
        json={
            "investment_type": "Renta fija",
            "institution": "Institución demo",
            "amount": 15000.75,
            "as_of_date": "2026-06-22",
        },
    )
    assert created.status_code == 201
    investment = created.json()
    assert investment["amount"] == 15000.75

    updated = client.put(
        f"/api/investments/{investment['id']}",
        json={"amount": 16000.25, "investment_type": "Fondo"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 16000.25
    assert updated.json()["investment_type"] == "Fondo"

    assert client.delete(f"/api/investments/{investment['id']}").status_code == 204
    assert client.get("/api/investments").json()["total"] == 0


def test_financial_pagination_and_account_filter(client):
    account = client.post(
        "/api/accounts",
        json={
            "name": "Cuenta paginada",
            "institution": "Banco demo",
            "account_type": "debit",
        },
    ).json()
    database = client.app.state.database
    with database.session() as db:
        db.add_all(
            [
                Transaction(
                    date=date(2026, 6, 22),
                    type="gasto",
                    category="Paginación",
                    name=f"Movimiento {index}",
                    amount_cents=100,
                    account_id=account["id"] if index < 3 else None,
                    source="manual",
                )
                for index in range(505)
            ]
        )
        db.commit()

    first = client.get("/api/transactions?category=Paginación&limit=200&offset=0").json()
    third = client.get("/api/transactions?category=Paginación&limit=200&offset=400").json()
    filtered = client.get(f"/api/transactions?account_id={account['id']}").json()

    assert first["total"] == 505
    assert len(first["items"]) == 200
    assert len(third["items"]) == 105
    assert filtered["total"] == 3
