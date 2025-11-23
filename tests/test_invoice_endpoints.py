from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def _signup_and_get_token():
    # Minimal auth flow (phone only)
    phone = "+2349990001112"
    r = client.post("/auth/signup/request", json={"phone": phone, "name": "InvUser"})
    assert r.status_code == 200
    # Extract OTP from in-memory store
    from app.services.otp_service import OTPService
    svc = OTPService()
    raw = svc._store.get(f"otp:signup:{phone}")  # type: ignore[attr-defined]
    assert raw is not None
    import json
    code = json.loads(raw)["code"]
    v = client.post("/auth/signup/verify", json={"phone": phone, "otp": code})
    assert v.status_code == 200, v.text
    token = v.json()["access_token"]

    # Ensure bank details exist so revenue invoices pass validation
    headers = _auth_headers(token)
    bank_payload = {
        "business_name": "Test Biz",
        "bank_name": "SuoOps Bank",
        "account_number": "0001234567",
        "account_name": "Test Biz",
    }
    bd = client.patch("/users/me/bank-details", json=bank_payload, headers=headers)
    assert bd.status_code == 200, bd.text

    return token


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


@patch("app.workers.tasks.generate_invoice_pdf_async.delay", MagicMock())
def test_create_and_verify_invoice_flow():
    token = _signup_and_get_token()
    headers = _auth_headers(token)

    # Create invoice
    payload = {
        "customer_name": "Alice",
        "customer_phone": "+2348001112222",
        "amount": 15000,
        "due_date": None,
    }
    ci = client.post("/invoices/", json=payload, headers=headers)
    assert ci.status_code == 200, ci.text
    inv = ci.json()
    assert "invoice_id" in inv and inv["status"] == "pending"

    # Fetch detail
    gd = client.get(f"/invoices/{inv['invoice_id']}", headers=headers)
    assert gd.status_code == 200
    detail = gd.json()
    assert detail["invoice_id"] == inv["invoice_id"]
    assert "lines" in detail

    # Public verify endpoint (no auth)
    ver = client.get(f"/invoices/{inv['invoice_id']}/verify")
    assert ver.status_code == 200, ver.text
    vj = ver.json()
    assert vj["invoice_id"] == inv["invoice_id"]
    assert vj["authentic"] is True
    assert vj["customer_name"].startswith("A")  # masked


@patch("app.workers.tasks.generate_invoice_pdf_async.delay", MagicMock())
def test_update_invoice_status():
    token = _signup_and_get_token()
    headers = _auth_headers(token)
    payload = {
        "customer_name": "Bob",
        "customer_phone": "+2348002223333",
        "amount": 5000,
    }
    ci = client.post("/invoices/", json=payload, headers=headers)
    assert ci.status_code == 200
    inv = ci.json()

    # Update status to paid
    up = client.patch(f"/invoices/{inv['invoice_id']}", json={"status": "paid"}, headers=headers)
    assert up.status_code == 200, up.text
    upd = up.json()
    assert upd["status"] == "paid"

    # List invoices should include updated status
    li = client.get("/invoices/", headers=headers)
    assert li.status_code == 200
    listed = li.json()
    assert any(i["invoice_id"] == inv["invoice_id"] and i["status"] == "paid" for i in listed)
