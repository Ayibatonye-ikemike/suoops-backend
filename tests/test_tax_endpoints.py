import json
import secrets
from fastapi.testclient import TestClient

from app.api.main import app
from app.services.otp_service import OTPService


def _extract_otp(phone: str, purpose: str) -> str:
    service = OTPService()
    raw = service._store.get(f"otp:{purpose}:{phone}")  # type: ignore[attr-defined]
    assert raw is not None
    data = json.loads(raw)
    return data["code"]


def _auth_client() -> tuple[TestClient, str]:
    client = TestClient(app)
    phone = "+234" + secrets.token_hex(4)
    # signup
    # Provide business_name to satisfy non-null constraints if any and ensure phone persists
    r = client.post("/auth/signup/request", json={"phone": phone, "name": "TaxUser", "business_name": "Test Biz"})
    assert r.status_code == 200, r.text
    otp = _extract_otp(phone, "signup")
    v = client.post("/auth/signup/verify", json={"phone": phone, "otp": otp})
    assert v.status_code == 200, v.text
    access = v.json()["access_token"]
    return client, access


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_tax_profile_and_compliance_endpoints():
    client, token = _auth_client()
    headers = _auth_headers(token)

    # /tax/profile
    prof = client.get("/tax/profile", headers=headers)
    assert prof.status_code == 200, prof.text
    jp = prof.json()
    assert "business_size" in jp and "classification" in jp and "tax_rates" in jp

    # /tax/small-business-check
    sb = client.get("/tax/small-business-check", headers=headers)
    assert sb.status_code == 200, sb.text
    jsb = sb.json()
    assert "eligible" in jsb and "business_size" in jsb and "tax_rates" in jsb

    # /tax/compliance
    comp = client.get("/tax/compliance", headers=headers)
    assert comp.status_code == 200, comp.text
    jc = comp.json()
    assert "compliance_status" in jc and "requirements" in jc

    # /tax/vat/summary
    vat = client.get("/tax/vat/summary", headers=headers)
    assert vat.status_code == 200, vat.text
    jv = vat.json()
    assert "current_month" in jv and "registered" in jv
    assert "tax_period" in jv["current_month"]


def test_tax_profile_update_returns_summary():
    client, token = _auth_client()
    headers = _auth_headers(token)

    upd = client.post(
        "/tax/profile",
        json={"annual_turnover": 5000000, "fixed_assets": 1000000},
        headers=headers,
    )
    assert upd.status_code == 200, upd.text
    ju = upd.json()
    assert ju.get("message") == "Tax profile updated successfully"
    assert "summary" in ju
    assert "classification" in ju["summary"]
