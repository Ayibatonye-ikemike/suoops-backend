import secrets

from fastapi.testclient import TestClient

from app.api.main import app

PASSWORD = "Pass1234!"


def test_register_and_login():
    client = TestClient(app)
    phone = "+234" + secrets.token_hex(4)
    reg = client.post(
        "/auth/register",
        json={"phone": phone, "name": "UserA", "password": PASSWORD},
    )
    assert reg.status_code == 200, reg.text
    login = client.post("/auth/login", json={"phone": phone, "password": PASSWORD})
    assert login.status_code == 200
    data = login.json()
    assert data["token_type"] == "bearer"
    assert "access_expires_at" in data
    cookie = login.cookies.get("whatsinvoice.refresh")
    assert cookie is not None
