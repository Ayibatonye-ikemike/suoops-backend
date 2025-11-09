from __future__ import annotations

from decimal import Decimal
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.session import get_db
from app.models.models import User, Customer, Invoice


def _setup_entities(db):
    user = User(phone="+234000000001", name="Test Biz")
    db.add(user); db.commit(); db.refresh(user)
    cust = Customer(name="CSV Customer")
    db.add(cust); db.commit(); db.refresh(cust)
    inv1 = Invoice(
        invoice_id="INV-CSV-1",
        issuer_id=user.id,
        customer_id=cust.id,
        amount=Decimal("10000"),
        discount_amount=Decimal("1000"),
        status="paid",
        vat_rate=7.5,
        vat_amount=Decimal("675"),
        vat_category="standard",
    )
    inv2 = Invoice(
        invoice_id="INV-CSV-2",
        issuer_id=user.id,
        customer_id=cust.id,
        amount=Decimal("5000"),
        status="paid",
        vat_rate=7.5,
        vat_amount=Decimal("375"),
        vat_category="standard",
    )
    db.add_all([inv1, inv2]); db.commit()
    return user


def test_monthly_tax_report_csv_export(monkeypatch):
    client = TestClient(app)
    db = next(get_db())
    user = _setup_entities(db)
    from app.api import routes_auth
    app.dependency_overrides[routes_auth.get_current_user_id] = lambda: user.id
    headers = {"Authorization": "Bearer test"}
    r = client.post("/tax/reports/generate?year=2025&month=10&basis=paid", headers=headers)
    assert r.status_code == 200, r.text
    rcsv = client.get("/tax/reports/2025/10/csv?basis=paid", headers=headers)
    assert rcsv.status_code == 200, rcsv.text
    payload = rcsv.json()
    assert "csv_url" in payload
    assert payload["basis"] == "paid"