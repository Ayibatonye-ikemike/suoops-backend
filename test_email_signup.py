"""Test email-based signup (temporary pre-launch feature)."""

import requests
import os
import pytest

API_URL = "https://suoops-backend-e4a267e41e92.herokuapp.com"

@pytest.mark.integration
def test_email_signup_flow():
    """Integration test for email OTP signup flow (request phase only)."""
    if not os.getenv("INTEGRATION"):
        pytest.skip("Skipping email signup integration test (set INTEGRATION=1 to run)")
    print("🧪 Testing Email Signup...")
    print("=" * 50)
    response = requests.post(
        f"{API_URL}/signup/request",
        json={
            "email": "test@example.com",
            "name": "Test User",
            "business_name": "Test Business"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    if response.status_code == 200:
        assert response.json().get("detail") is not None
    else:
        pytest.fail(f"OTP request failed: {response.status_code} {response.text}")
    print("🎯 Email OTP is live (request succeeded)!")

if __name__ == "__main__":  # pragma: no cover
    test_email_signup_flow()
