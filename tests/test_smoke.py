import secrets

from fastapi.testclient import TestClient

from app.api.main import app


def _register_and_login(client: TestClient):
    phone = "+234" + secrets.token_hex(4)
    reg = client.post(
        "/auth/register", json={"phone": phone, "name": "SmokeUser", "password": "Pass1234"}
    )
    assert reg.status_code == 200, reg.text
    login = client.post("/auth/login", json={"phone": phone, "password": "Pass1234"})
    assert login.status_code == 200, login.text
    payload = login.json()
    token = payload["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_list_invoice_auth_flow():
    client = TestClient(app)
    headers = _register_and_login(client)
    resp = client.post(
        "/invoices/",
        json={
            "customer_name": "Test Customer",
            "amount": "1500",
            "lines": [{"description": "Service", "quantity": 1, "unit_price": "1500"}],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    invoice_id = resp.json()["invoice_id"]
    resp2 = client.get("/invoices/", headers=headers)
    assert resp2.status_code == 200
    assert any(inv["invoice_id"] == invoice_id for inv in resp2.json())


def test_invoice_detail_status_flow():
    client = TestClient(app)
    headers = _register_and_login(client)
    create_resp = client.post(
        "/invoices/",
        json={
            "customer_name": "Detail Customer",
            "amount": "5000",
            "lines": [{"description": "Consulting", "quantity": 2, "unit_price": "2500"}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    invoice_id = create_resp.json()["invoice_id"]

    detail = client.get(f"/invoices/{invoice_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["invoice_id"] == invoice_id
    assert body["customer"]["name"] == "Detail Customer"
    assert len(body["lines"]) == 1

    status_update = client.patch(
        f"/invoices/{invoice_id}",
        json={"status": "failed"},
        headers=headers,
    )
    assert status_update.status_code == 200, status_update.text
    assert status_update.json()["status"] == "failed"

    bad_status = client.patch(
        f"/invoices/{invoice_id}",
        json={"status": "unsupported"},
        headers=headers,
    )
    assert bad_status.status_code == 422

    # Events endpoint removed because invoices rely on manual confirmation


def test_public_invoice_confirmation_flow():
    client = TestClient(app)
    headers = _register_and_login(client)
    create_resp = client.post(
        "/invoices/",
        json={
            "customer_name": "Public Customer",
            "amount": "7500",
            "lines": [{"description": "Design", "quantity": 1, "unit_price": "7500"}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    invoice_id = create_resp.json()["invoice_id"]

    public_view = client.get(f"/public/invoices/{invoice_id}")
    assert public_view.status_code == 200, public_view.text
    assert public_view.json()["status"] == "pending"

    confirm_resp = client.post(f"/public/invoices/{invoice_id}/confirm-transfer")
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["status"] == "awaiting_confirmation"

    detail = client.get(f"/invoices/{invoice_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "awaiting_confirmation"

    mark_paid = client.patch(
        f"/invoices/{invoice_id}",
        json={"status": "paid"},
        headers=headers,
    )
    assert mark_paid.status_code == 200, mark_paid.text
    assert mark_paid.json()["status"] == "paid"
