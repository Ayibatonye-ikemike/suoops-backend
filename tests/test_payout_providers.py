"""Payout provider abstraction: factory + Paystack/Flutterwave payload shape."""
from types import SimpleNamespace


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


class _FakeClient:
    """Minimal httpx.Client stand-in dispatching to a handler(method, url, body)."""

    def __init__(self, handler):
        self._h = handler

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, headers=None, params=None):
        return self._h("GET", url, None)

    def post(self, url, headers=None, json=None):
        return self._h("POST", url, json)


def test_factory_selects_provider(monkeypatch):
    from app.core.config import settings
    from app.services.payouts import get_payout_provider

    monkeypatch.setattr(settings, "ESCROW_PAYOUT_PROVIDER", "flutterwave")
    assert get_payout_provider().name == "flutterwave"
    monkeypatch.setattr(settings, "ESCROW_PAYOUT_PROVIDER", "paystack")
    assert get_payout_provider().name == "paystack"
    # Unknown value falls back to Paystack.
    monkeypatch.setattr(settings, "ESCROW_PAYOUT_PROVIDER", "totally-unknown")
    assert get_payout_provider().name == "paystack"


def test_paystack_transfer_uses_cached_recipient(monkeypatch):
    from app.core.config import settings
    import app.services.payouts.paystack as ps

    monkeypatch.setattr(settings, "PAYSTACK_SECRET", "sk_test_x")
    captured = {}

    def handler(method, url, body):
        captured["url"] = url
        captured["body"] = body
        return _Resp({"status": True, "message": "ok"})

    monkeypatch.setattr(ps.httpx, "Client", lambda *a, **k: _FakeClient(handler))

    seller = SimpleNamespace(
        id=1,
        paystack_recipient_code="RCP_cached",  # no recipient-creation call
        payout_account_number=None,
        payout_bank_name=None,
        account_number="0123456789",
        bank_name="GTBank",
        account_name="X",
        business_name="X",
        name="X",
    )
    db = SimpleNamespace(commit=lambda: None)
    res = ps.PaystackPayoutProvider().transfer(
        db, seller=seller, amount_kobo=50000, reference="REF1", reason="r"
    )
    assert res.ok is True and res.provider == "paystack"
    assert captured["url"].endswith("/transfer")
    assert captured["body"]["amount"] == 50000  # Paystack uses kobo
    assert captured["body"]["recipient"] == "RCP_cached"
    assert captured["body"]["source"] == "balance"
    assert captured["body"]["reference"] == "REF1"


def test_flutterwave_transfer_converts_amount_and_resolves_bank(monkeypatch):
    from app.core.config import settings
    import app.services.payouts.flutterwave as fw

    monkeypatch.setattr(settings, "FLUTTERWAVE_SECRET", "FLWSECK_test")
    monkeypatch.setattr(fw, "_fw_bank_cache", {})
    monkeypatch.setattr(fw, "_fw_bank_cache_at", 0.0)
    posts = {}

    def handler(method, url, body):
        if method == "GET":  # bank list
            return _Resp({"status": "success", "data": [{"code": "058", "name": "GTBank"}]})
        posts["url"] = url
        posts["body"] = body
        return _Resp({"status": "success", "message": "Transfer Queued"})

    monkeypatch.setattr(fw.httpx, "Client", lambda *a, **k: _FakeClient(handler))

    seller = SimpleNamespace(
        id=2,
        payout_account_number=None,
        payout_bank_name=None,
        account_number="0123456789",
        bank_name="GTBank",
    )
    db = SimpleNamespace(commit=lambda: None)
    res = fw.FlutterwavePayoutProvider().transfer(
        db, seller=seller, amount_kobo=50000, reference="REF2", reason="r"
    )
    assert res.ok is True and res.provider == "flutterwave"
    assert posts["url"].endswith("/v3/transfers")
    assert posts["body"]["amount"] == 500.0  # 50000 kobo -> ₦500 (major unit)
    assert posts["body"]["account_bank"] == "058"
    assert posts["body"]["account_number"] == "0123456789"
    assert posts["body"]["reference"] == "REF2"
