import secrets

from fastapi.testclient import TestClient

from app.api.main import app

PASSWORD = "Pass1234!"


def _auth_headers(client: TestClient):
    phone = "+234" + secrets.token_hex(4)
    reg = client.post(
        "/auth/register",
        json={"phone": phone, "name": "PayrollUser", "password": PASSWORD},
    )
    assert reg.status_code == 200, reg.text
    login = client.post("/auth/login", json={"phone": phone, "password": PASSWORD})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_payroll_worker_and_run():
    client = TestClient(app)
    headers = _auth_headers(client)

    worker = client.post(
        "/payroll/workers",
        json={"name": "Worker A", "daily_rate": "5000"},
        headers=headers,
    ).json()
    assert worker["name"] == "Worker A"
    wid = worker["id"]

    run = client.post(
        "/payroll/runs",
        json={"period_label": "2025-10-W41", "days": {str(wid): 5}},
        headers=headers,
    ).json()
    assert run["period_label"] == "2025-10-W41"
    assert run["total_gross"] == "25000"
    assert len(run["records"]) == 1


def test_payroll_run_skips_unknown_worker():
    client = TestClient(app)
    headers = _auth_headers(client)
    run = client.post(
        "/payroll/runs",
        json={"period_label": "2025-10-W41", "days": {"999999": 3}},
        headers=headers,
    ).json()
    # No records because worker does not exist
    assert run["total_gross"] == "0"
    assert run["records"] == []


def test_list_workers():
    """Test GET /payroll/workers endpoint."""
    client = TestClient(app)
    headers = _auth_headers(client)

    # Initially should be empty
    workers = client.get("/payroll/workers", headers=headers).json()
    assert workers == []

    # Add a worker
    worker1 = client.post(
        "/payroll/workers",
        json={"name": "Alice", "daily_rate": "3000"},
        headers=headers,
    ).json()
    assert worker1["name"] == "Alice"

    # Add another worker
    worker2 = client.post(
        "/payroll/workers",
        json={"name": "Bob", "daily_rate": "4000"},
        headers=headers,
    ).json()
    assert worker2["name"] == "Bob"

    # List should return both workers
    workers = client.get("/payroll/workers", headers=headers).json()
    assert len(workers) == 2
    names = {w["name"] for w in workers}
    assert names == {"Alice", "Bob"}
