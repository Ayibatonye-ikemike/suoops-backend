"""Escrow trust + window unit tests (step 3)."""
import datetime as dt

from app.services import escrow_service as es


def test_hold_window_same_vs_cross_state():
    assert es.hold_window(True) == dt.timedelta(hours=12)
    assert es.hold_window(False) == dt.timedelta(days=3)


def test_buyer_reputation_tracks_and_flags():
    """Disputes accumulate; enough false disputes flags the buyer."""
    import secrets

    from app.core.config import settings
    from app.db.session import SessionLocal

    phone = "+23480" + "".join(secrets.choice("0123456789") for _ in range(7))
    s = SessionLocal()
    try:
        es.record_buyer_dispute(s, phone)
        rep = es.get_buyer_reputation(s, phone)
        assert rep is not None and rep.disputes == 1 and rep.false_disputes == 0
        assert rep.flagged is False
        # Cross the false-dispute threshold → flagged.
        for _ in range(settings.ESCROW_BUYER_ABUSE_FLAG_AT):
            es.record_buyer_false_dispute(s, phone)
        rep = es.get_buyer_reputation(s, phone)
        assert rep.false_disputes >= settings.ESCROW_BUYER_ABUSE_FLAG_AT
        assert rep.flagged is True
    finally:
        s.rollback()
        s.close()


def test_detect_order_collusion():
    """Self-dealing signals: buyer shares the seller's IP or sits on the store."""
    from types import SimpleNamespace

    seller = SimpleNamespace(
        signup_ip="102.89.1.1",
        storefront_lat=6.5000,
        storefront_lng=3.3000,
    )
    # Shared IP → flagged.
    assert es.detect_order_collusion(
        seller, buyer_ip="102.89.1.1", customer_lat=None, customer_lng=None
    ) == "shared IP"
    # Buyer GPS on top of the store (~15m) → flagged.
    assert "seller location" in (
        es.detect_order_collusion(
            seller, buyer_ip="10.0.0.9", customer_lat=6.5001, customer_lng=3.3001
        )
        or ""
    )
    # Different IP + far location → clean.
    assert es.detect_order_collusion(
        seller, buyer_ip="10.0.0.9", customer_lat=7.4, customer_lng=4.1
    ) is None


def test_release_blocked_when_held_for_review():
    """A collusion/anomaly-flagged order never auto-releases."""
    from types import SimpleNamespace

    import pytest

    from app.db.session import SessionLocal

    s = SessionLocal()
    try:
        with pytest.raises(es.EscrowError):
            es.release_escrow(
                s, SimpleNamespace(id=99, status="held", held_for_review=True)
            )
    finally:
        s.close()


def test_release_blocked_when_payout_frozen():
    """Payouts are refused while a seller's post-bank-change freeze is active."""
    from types import SimpleNamespace

    import pytest

    from app.db.session import SessionLocal
    from app.models import models

    s = SessionLocal()
    try:
        seller = models.User(name="Frozen Seller", phone="+2349995551212")
        seller.payout_frozen_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5)
        s.add(seller)
        s.commit()
        s.refresh(seller)
        escrow = SimpleNamespace(
            id=123,
            status="held",
            held_for_review=False,
            payout_kobo=50000,
            seller_id=seller.id,
        )
        with pytest.raises(es.EscrowError):
            es.release_escrow(s, escrow)
    finally:
        s.rollback()
        s.close()


def test_release_escrow_status_guards():
    """release_escrow short-circuits (no Paystack) for non-releasable states."""
    from types import SimpleNamespace

    from app.db.session import SessionLocal

    s = SessionLocal()
    try:
        assert es.release_escrow(s, SimpleNamespace(status="released")) is True
        assert es.release_escrow(s, SimpleNamespace(status="pending")) is False
        assert es.release_escrow(s, SimpleNamespace(status="disputed")) is False
        assert es.release_escrow(s, SimpleNamespace(status="refunded")) is False
    finally:
        s.close()


def _fake_provider_class():
    """A PayoutProvider whose transfer() queues (pending) and whose
    transfer_status() is script-controlled per reference."""
    from app.services.payouts.base import PayoutProvider, PayoutResult

    class FakeProvider(PayoutProvider):
        name = "fake"

        def __init__(self):
            self.sent = []
            self.status_map = {}

        def transfer(self, db, *, seller, amount_kobo, reference, reason):
            self.sent.append(reference)
            self.status_map.setdefault(reference, "pending")
            return PayoutResult(
                ok=True, reference=reference, provider=self.name, status="pending"
            )

        def transfer_status(self, reference):
            return self.status_map.get(reference, "unknown")

    return FakeProvider


def _held_escrow(seller_id):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=555,
        status="held",
        held_for_review=False,
        payout_kobo=50000,
        seller_id=seller_id,
        invoice_id=1,
        transfer_reference=None,
        released_at=None,
        charge_reference=None,
    )


def test_release_waits_for_confirmation_then_releases(monkeypatch):
    """A queued (pending) transfer stays 'held'; a later 'successful' releases it
    WITHOUT re-sending."""
    import app.services.payouts as payouts
    from app.db.session import SessionLocal
    from app.models import models

    fake = _fake_provider_class()()
    monkeypatch.setattr(payouts, "get_payout_provider", lambda: fake)

    s = SessionLocal()
    try:
        seller = models.User(
            name="Payout Seller", phone="+2348000000001",
            account_number="0123456789", bank_name="GTBank",
        )
        s.add(seller)
        s.commit()
        s.refresh(seller)
        escrow = _held_escrow(seller.id)

        # Run 1: queued → in flight → stays held, not released.
        assert es.release_escrow(s, escrow) is False
        assert escrow.status == "held"
        assert escrow.transfer_reference == "ESCROWREL-555"
        assert fake.sent == ["ESCROWREL-555"]

        # Run 2: provider now confirms success → released, no second transfer.
        fake.status_map["ESCROWREL-555"] = "successful"
        assert es.release_escrow(s, escrow) is True
        assert escrow.status == "released"
        assert fake.sent == ["ESCROWREL-555"]  # never re-sent
    finally:
        s.rollback()
        s.close()


def test_release_retries_failed_transfer_with_fresh_reference(monkeypatch):
    """A confirmed-failed transfer is retried with a NEW (unburned) reference."""
    import app.services.payouts as payouts
    from app.db.session import SessionLocal
    from app.models import models

    fake = _fake_provider_class()()
    monkeypatch.setattr(payouts, "get_payout_provider", lambda: fake)

    s = SessionLocal()
    try:
        seller = models.User(
            name="Retry Seller", phone="+2348000000002",
            account_number="0123456789", bank_name="GTBank",
        )
        s.add(seller)
        s.commit()
        s.refresh(seller)
        escrow = _held_escrow(seller.id)

        # Run 1: send deterministic ref, stays pending.
        assert es.release_escrow(s, escrow) is False
        assert fake.sent == ["ESCROWREL-555"]

        # The first transfer failed → next run must use a fresh reference.
        fake.status_map["ESCROWREL-555"] = "failed"
        assert es.release_escrow(s, escrow) is False
        assert len(fake.sent) == 2
        assert fake.sent[1] != fake.sent[0]
        assert fake.sent[1].startswith("ESCROWREL-555-")
        assert escrow.status == "held"
    finally:
        s.rollback()
        s.close()


def test_release_does_not_resend_on_unknown_status(monkeypatch):
    """An indeterminate ('unknown') prior status never triggers a re-send."""
    import app.services.payouts as payouts
    from app.db.session import SessionLocal
    from app.models import models

    fake = _fake_provider_class()()
    monkeypatch.setattr(payouts, "get_payout_provider", lambda: fake)

    s = SessionLocal()
    try:
        seller = models.User(
            name="Unknown Seller", phone="+2348000000003",
            account_number="0123456789", bank_name="GTBank",
        )
        s.add(seller)
        s.commit()
        s.refresh(seller)
        escrow = _held_escrow(seller.id)

        assert es.release_escrow(s, escrow) is False
        assert fake.sent == ["ESCROWREL-555"]

        # Status can't be determined → must WAIT, not re-send (no double pay).
        fake.status_map["ESCROWREL-555"] = "unknown"
        assert es.release_escrow(s, escrow) is False
        assert fake.sent == ["ESCROWREL-555"]  # still only one transfer
        assert escrow.status == "held"
    finally:
        s.rollback()
        s.close()


def test_release_uses_collecting_rail(monkeypatch):
    """Release must pay out through the SAME provider that collected the order —
    a Flutterwave-collected order pays out from Flutterwave, not the default."""
    import app.services.escrow_service as escrow_mod
    import app.services.payouts as payouts
    from app.db.session import SessionLocal
    from app.models import models
    from app.services.payouts.base import PayoutResult

    captured = {}

    def _named(name):
        captured["name"] = name
        prov = _fake_provider_class()()

        def _confirming_transfer(db, *, seller, amount_kobo, reference, reason):
            prov.sent.append(reference)
            return PayoutResult(
                ok=True, reference=reference, provider="flutterwave", status="successful"
            )

        prov.transfer = _confirming_transfer
        return prov

    monkeypatch.setattr(escrow_mod, "_collector_for_charge", lambda db, ref: "flutterwave")
    monkeypatch.setattr(payouts, "get_payout_provider_named", _named)

    s = SessionLocal()
    try:
        seller = models.User(
            name="Rail Seller", phone="+2348000000009",
            account_number="0123456789", bank_name="GTBank",
        )
        s.add(seller)
        s.commit()
        s.refresh(seller)

        from types import SimpleNamespace

        escrow = SimpleNamespace(
            id=777,
            status="held",
            held_for_review=False,
            payout_kobo=50000,
            seller_id=seller.id,
            invoice_id=1,
            transfer_reference=None,
            released_at=None,
            charge_reference="INVPAY-RAIL-1",
        )

        assert es.release_escrow(s, escrow) is True
        assert escrow.status == "released"
        assert captured["name"] == "flutterwave"
    finally:
        s.rollback()
        s.close()


def test_release_resends_when_rail_changed(monkeypatch):
    """A reference from a different (failed) rail must NOT be reconciled as
    'in flight' — release starts a fresh transfer on the CURRENT rail."""
    import app.services.escrow_service as escrow_mod
    import app.services.payouts as payouts
    from app.db.session import SessionLocal
    from app.models import models
    from app.services.payouts.base import PayoutResult

    sent: list[str] = []

    class _FW:
        name = "flutterwave"

        def transfer_status(self, reference):
            return "unknown"  # the old Paystack ref doesn't exist on Flutterwave

        def transfer(self, db, *, seller, amount_kobo, reference, reason):
            sent.append(reference)
            return PayoutResult(
                ok=True, reference=reference, provider="flutterwave", status="successful"
            )

        def transfer_exists(self, reference):
            return True

    monkeypatch.setattr(escrow_mod, "_collector_for_charge", lambda db, ref: "flutterwave")
    monkeypatch.setattr(payouts, "get_payout_provider_named", lambda name: _FW())

    s = SessionLocal()
    try:
        seller = models.User(
            name="Rail Change Seller", phone="+2348000000010",
            account_number="0123456789", bank_name="GTBank",
        )
        s.add(seller)
        s.commit()
        s.refresh(seller)

        from types import SimpleNamespace

        escrow = SimpleNamespace(
            id=888,
            status="held",
            held_for_review=False,
            payout_kobo=50000,
            seller_id=seller.id,
            invoice_id=1,
            transfer_reference="ESCROWREL-888",  # burned on the old (Paystack) rail
            transfer_provider="paystack",
            released_at=None,
            charge_reference="INVPAY-RAIL-CHG",
        )

        # Must NOT read the 'unknown' status as in-flight — it sends fresh + releases.
        assert es.release_escrow(s, escrow) is True
        assert escrow.status == "released"
        assert len(sent) == 1
        assert sent[0].startswith("ESCROWREL-888-")  # fresh reference, not the burned one
        assert escrow.transfer_provider == "flutterwave"
    finally:
        s.rollback()
        s.close()


def test_refund_escrow_status_guards():
    """refund_escrow is idempotent and refuses to refund an already-paid order."""
    from types import SimpleNamespace

    import pytest

    from app.db.session import SessionLocal

    s = SessionLocal()
    try:
        assert es.refund_escrow(s, SimpleNamespace(status="refunded")) is True
        with pytest.raises(es.EscrowError):
            es.refund_escrow(s, SimpleNamespace(id=1, status="released"))
        with pytest.raises(es.EscrowError):
            es.refund_escrow(s, SimpleNamespace(id=2, status="disputed", charge_reference=None))
    finally:
        s.close()


def test_fresh_seller_is_not_trusted():
    """A brand-new seller (young account, no paid invoices) must NOT be trusted,
    so their storefront orders are always held."""
    from app.db.session import SessionLocal
    from app.models import models

    s = SessionLocal()
    try:
        u = models.User(name="Fresh Seller", phone="+2349990009090")
        s.add(u)
        s.commit()
        s.refresh(u)
        try:
            assert es.is_trusted_seller(s, u) is False
        finally:
            s.delete(u)
            s.commit()
    finally:
        s.close()


def test_activate_escrow_sets_held_and_window():
    """On payment, a pending same-state hold becomes 'held' with a 12h window."""
    from decimal import Decimal

    from app.db.session import SessionLocal
    from app.models import models

    s = SessionLocal()
    try:
        seller = models.User(name="Seller", phone="+2349990008080", storefront_state="Lagos")
        s.add(seller)
        s.commit()
        s.refresh(seller)

        customer = models.Customer(name="Buyer")
        s.add(customer)
        s.commit()
        s.refresh(customer)

        paid_at = dt.datetime(2026, 7, 8, 10, 0, tzinfo=dt.timezone.utc)
        inv = models.Invoice(
            invoice_id="EXP-ESCROWTEST-1",
            issuer_id=seller.id,
            customer_id=customer.id,
            amount=Decimal("5000"),
            status="paid",
            paid_at=paid_at,
            invoice_type="revenue",
            channel="storefront",
        )
        s.add(inv)
        s.commit()
        s.refresh(inv)

        esc = models.StorefrontOrderEscrow(
            invoice_id=inv.id,
            seller_id=seller.id,
            status="pending",
            same_state=True,
            gross_kobo=500000,
            fee_kobo=15000,
            payout_kobo=485000,
        )
        s.add(esc)
        s.commit()
        s.refresh(esc)

        try:
            es.activate_escrow_on_payment(s, inv)
            s.refresh(esc)
            assert esc.status == "held"
            expected = paid_at + dt.timedelta(hours=12)
            # Test DB (SQLite) strips tzinfo — compare naive to naive.
            assert esc.release_due_at.replace(tzinfo=None) == expected.replace(tzinfo=None)
        finally:
            s.delete(esc)
            s.delete(inv)
            s.delete(customer)
            s.delete(seller)
            s.commit()
    finally:
        s.close()
