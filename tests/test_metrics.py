from fastapi.testclient import TestClient

from app.api.main import app


def test_metrics_endpoint_available():
    client = TestClient(app)
    resp = client.get("/metrics")
    # If prometheus_client installed we expect 200, else 503 fallback
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        text = resp.text
        # Basic sanity checks for some known metric names
        assert "invoice_created_total" in text
        assert "otp_signup_requests_total" in text
        assert "otp_login_verifications_total" in text
        # New instrumentation
        assert "otp_invalid_attempts_total" in text
        assert "otp_signup_verify_latency_seconds" in text
        assert "otp_login_verify_latency_seconds" in text
        # Delivery metrics
        assert "otp_whatsapp_delivery_success_total" in text
        assert "otp_email_delivery_success_total" in text
        assert "otp_resend_success_conversion_total" in text
        # Bucket boundary sanity (one mid bucket)
        assert (
            'otp_signup_verify_latency_seconds_bucket{le="30"}' in text
            or 'otp_signup_verify_latency_seconds_bucket{le="30.0"}' in text
        )
    else:
        assert "prometheus" in resp.text.lower()
