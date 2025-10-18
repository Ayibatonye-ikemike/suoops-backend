import hashlib
import hmac
import json
import secrets

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import settings

PASSWORD = "Pass1234!"


def _auth_headers(client: TestClient) -> dict[str, str]:
    phone = "+234" + secrets.token_hex(4)
    register = client.post(
        "/auth/register",
        json={"phone": phone, "name": "PUser", "password": PASSWORD},
    )
    assert register.status_code == 200, register.text
    login = client.post("/auth/login", json={"phone": phone, "password": PASSWORD})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_invoice(client: TestClient, headers: dict[str, str]) -> dict:
    resp = client.post(
        "/invoices/",
        json={"customer_name": "Webhook Test", "amount": "2500"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_paystack_webhook_idempotent():
    client = TestClient(app)
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers)
    invoice_id = invoice["invoice_id"]

    event = {"data": {"reference": invoice_id, "status": "success"}}
    raw = json.dumps(event).encode()
    sig = hmac.new(settings.PAYSTACK_SECRET.encode(), raw, hashlib.sha512).hexdigest()

    original_provider = settings.PRIMARY_PAYMENT_PROVIDER
    settings.PRIMARY_PAYMENT_PROVIDER = "flutterwave"
    try:
        first = client.post(
            "/webhooks/paystack",
            content=raw,
            headers={"x-paystack-signature": sig},
        )
        assert first.status_code == 200, first.text
        assert first.json()["ok"] is True

        duplicate = client.post(
            "/webhooks/paystack",
            content=raw,
            headers={"x-paystack-signature": sig},
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json().get("duplicate") is True
    finally:
        settings.PRIMARY_PAYMENT_PROVIDER = original_provider

    listed = client.get("/invoices/", headers=headers).json()
    target = next(i for i in listed if i["invoice_id"] == invoice_id)
    assert target["status"] == "paid"


def test_paystack_webhook_rejects_invalid_signature():
    client = TestClient(app)
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers)
    invoice_id = invoice["invoice_id"]

    event = {"data": {"reference": invoice_id, "status": "success"}}
    raw = json.dumps(event).encode()

    resp = client.post(
        "/webhooks/paystack",
        content=raw,
        headers={"x-paystack-signature": "invalid"},
    )
    assert resp.status_code == 400

    listed = client.get("/invoices/", headers=headers).json()
    target = next(i for i in listed if i["invoice_id"] == invoice_id)
    assert target["status"] == "pending"


def test_flutterwave_webhook_processes_and_idempotent():
    client = TestClient(app)
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers)
    invoice_id = invoice["invoice_id"]

    event = {
        "data": {
            "id": "flw-event-1",
            "tx_ref": invoice_id,
            "status": "success",
        }
    }
    raw = json.dumps(event).encode()
    sig = settings.FLUTTERWAVE_SECRET

    original_provider = settings.PRIMARY_PAYMENT_PROVIDER
    settings.PRIMARY_PAYMENT_PROVIDER = "paystack"
    try:
        first = client.post(
            "/webhooks/flutterwave",
            content=raw,
            headers={"verif-hash": sig},
        )
        assert first.status_code == 200, first.text
        assert first.json()["ok"] is True

        duplicate = client.post(
            "/webhooks/flutterwave",
            content=raw,
            headers={"verif-hash": sig},
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json().get("duplicate") is True
    finally:
        settings.PRIMARY_PAYMENT_PROVIDER = original_provider

    listed = client.get("/invoices/", headers=headers).json()
    target = next(i for i in listed if i["invoice_id"] == invoice_id)
    assert target["status"] == "paid"


def test_flutterwave_webhook_rejects_invalid_signature():
    client = TestClient(app)
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers)
    invoice_id = invoice["invoice_id"]

    event = {
        "data": {
            "id": "flw-event-2",
            "tx_ref": invoice_id,
            "status": "success",
        }
    }
    raw = json.dumps(event).encode()

    resp = client.post(
        "/webhooks/flutterwave",
        content=raw,
        headers={"verif-hash": "bad"},
    )
    assert resp.status_code == 400

    listed = client.get("/invoices/", headers=headers).json()
    target = next(i for i in listed if i["invoice_id"] == invoice_id)
    assert target["status"] == "pending"
