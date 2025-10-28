"""Test WhatsApp three-way flow from business to customer."""
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.bot.nlp_service import NLPService
from app.bot.whatsapp_adapter import WhatsAppClient, WhatsAppHandler
from app.models.models import User


@pytest.fixture
def whatsapp_text_payload():
    """Mock WhatsApp webhook payload for text message"""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "713163545130337",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550123456",
                                "phone_number_id": "817255254808254"
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Mike Business"},
                                    "wa_id": "2348012345678"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "2348012345678",  # Business owner's WhatsApp
                                    "id": "wamid.HBgNMjM0ODAxMjM0NTY3OBUCABIYIDNBMzQwNzE5RjQxNEE0",
                                    "timestamp": "1698432000",
                                    "text": {
                                        "body": "Invoice Jane Doe +2348087654321 50000 for logo design and branding"
                                    },
                                    "type": "text"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def whatsapp_voice_payload():
    """Mock WhatsApp webhook payload for voice note"""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "713163545130337",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550123456",
                                "phone_number_id": "817255254808254"
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Mike Business"},
                                    "wa_id": "2348012345678"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "2348012345678",  # Business owner's WhatsApp
                                    "id": "wamid.HBgNMjM0ODAxMjM0NTY3OBUCABIYIDNBMzQwNzE5RjQxNEE0",
                                    "timestamp": "1698432000",
                                    "type": "audio",
                                    "audio": {
                                        "mime_type": "audio/ogg; codecs=opus",
                                        "sha256": "abc123",
                                        "id": "1234567890",
                                        "voice": True
                                    }
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def business_user(db_session):
    """Create a business user with WhatsApp phone number."""
    user = User(
        phone="+2348012345678",  # Matches sender in webhook payload
        name="Mike Business",
    phone_verified=True,
        business_name="Mike's Design Studio",
        bank_name="GTBank",
        account_number="1234567890",
        account_name="Mike Business",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestWhatsAppThreeWayFlow:
    """Test complete Business → Bot → Customer flow"""

    def test_webhook_verification(self):
        """Test WhatsApp webhook verification (GET request from Meta)"""
        client = TestClient(app)
        
        # Meta sends GET request to verify webhook
        response = client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "suopay_verify_2025",
                "hub.challenge": "test_challenge_string"
            }
        )

        assert response.status_code == 200
        assert response.text == "test_challenge_string"

    def test_webhook_verification_fails_with_wrong_token(self):
        """Test webhook verification fails with incorrect token"""
        client = TestClient(app)
        
        response = client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "test_challenge_string"
            }
        )
        
        assert response.status_code == 403

    @patch('app.queue.whatsapp_queue.enqueue_message')
    def test_webhook_receives_message(self, mock_enqueue, whatsapp_text_payload):
        """Test webhook receives and queues incoming message"""
        client = TestClient(app)
        
        response = client.post(
            "/webhooks/whatsapp",
            json=whatsapp_text_payload
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True, "queued": True}

        # Verify message was enqueued for Celery processing
        mock_enqueue.assert_called_once_with(whatsapp_text_payload)

    def test_text_message_flow_complete(
        self,
        business_user,
        db_session,
        whatsapp_text_payload,
    ):
        """Ensure text messages create invoices and notify both parties."""
        mock_client = MagicMock(spec=WhatsAppClient)
        mock_client.send_template.return_value = False
        mock_client.send_document = MagicMock()

        handler = WhatsAppHandler(mock_client, NLPService(), db_session)
        handler.handle_webhook(whatsapp_text_payload)

        mock_client.send_text.assert_called()
        business_messages = [
            call.args
            for call in mock_client.send_text.call_args_list
            if call.args and call.args[0] == "+2348012345678"
        ]
        assert business_messages, "Expected at least one message to the business owner"
        assert any("Invoice" in msg[1] for msg in business_messages), "Invoice confirmation not sent to business"

        from app.models.models import Invoice

        invoice = (
            db_session.query(Invoice)
            .filter(Invoice.issuer_id == business_user.id)
            .first()
        )

        assert invoice is not None
        assert invoice.customer is not None
        assert invoice.customer.name == "Jane"
        assert invoice.customer.phone == "+2348087654321"
        assert invoice.amount == Decimal("50000")

    @patch('app.services.speech_service.SpeechService.transcribe_audio')
    def test_voice_note_flow_complete(
        self,
        mock_transcribe,
        business_user,
        db_session,
        whatsapp_voice_payload
    ):
        """Voice note messages should create invoices after transcription."""

        mock_transcribe.return_value = (
            "invoice jane doe zero eight zero eight seven six five four three two one "
            "fifty thousand naira for logo design"
        )

        mock_client = MagicMock(spec=WhatsAppClient)
        mock_client.get_media_url = AsyncMock(return_value="https://example.com/media")
        mock_client.download_media = AsyncMock(return_value=b"fake_audio_data")
        mock_client.send_template.return_value = False
        mock_client.send_document = MagicMock()

        handler = WhatsAppHandler(mock_client, NLPService(), db_session)
        handler.handle_webhook(whatsapp_voice_payload)

        mock_transcribe.assert_called_once()
        mock_client.send_text.assert_called()
        business_messages = [
            call.args
            for call in mock_client.send_text.call_args_list
            if call.args and call.args[0] == "+2348012345678"
        ]
        assert business_messages, "Expected at least one message to the business owner"
        assert any("Invoice" in msg[1] for msg in business_messages)

        from app.models.models import Invoice

        invoice = (
            db_session.query(Invoice)
            .filter(Invoice.issuer_id == business_user.id)
            .first()
        )

        assert invoice is not None
        assert invoice.customer is not None
        assert invoice.customer.phone == "+2348087654321"

    def test_unregistered_business_rejected(
        self,
        db_session,
        whatsapp_text_payload,
    ):
        """Unregistered businesses should receive actionable guidance."""
        mock_client = MagicMock(spec=WhatsAppClient)
        mock_client.send_template.return_value = False

        handler = WhatsAppHandler(mock_client, NLPService(), db_session)
        handler.handle_webhook(whatsapp_text_payload)

        mock_client.send_text.assert_called()
        message = mock_client.send_text.call_args[0][1]
        assert "Unable to identify your business account" in message
        assert "suopay.io/dashboard/settings" in message

    def test_missing_customer_phone_rejected(
        self,
        business_user,
        db_session,
    ):
        """Missing customer phone numbers should trigger validation help."""
        mock_client = MagicMock(spec=WhatsAppClient)
        mock_client.send_template.return_value = False

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "713163545130337",
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "2348012345678",
                                        "text": {
                                            "body": "Invoice Jane Doe 50000 for logo"
                                        },
                                        "type": "text",
                                    }
                                ]
                            },
                            "field": "messages",
                        }
                    ]
                }
            ],
        }

        handler = WhatsAppHandler(mock_client, NLPService(), db_session)
        handler.handle_webhook(payload)

        mock_client.send_text.assert_called()
        message = mock_client.send_text.call_args[0][1]
        assert "⚠️" in message
        assert "customer's phone number" in message
        assert "Example:" in message


class TestPhoneExtraction:
    """Test phone number extraction from various formats"""

    def test_extract_nigerian_phone_formats(self):
        """Test extraction of Nigerian phone numbers in different formats"""
        from app.bot.nlp_service import NLPService
        
        nlp = NLPService()
        
        test_cases = [
            ("Invoice Jane +2348087654321 50000", "+2348087654321"),
            ("Invoice Jane 2348087654321 50000", "+2348087654321"),
            ("Invoice Jane 08087654321 50000", "+2348087654321"),
            ("Invoice Jane 8087654321 50000", "+2348087654321"),
        ]
        
        for text, expected_phone in test_cases:
            extracted = nlp._extract_phone(text)
            assert extracted == expected_phone, f"Failed for: {text}"


class TestBusinessLookup:
    """Test business identification by phone number"""

    def test_resolve_business_by_exact_phone(self, business_user, db_session):
        """Test business lookup with exact phone match"""
        handler = WhatsAppHandler(WhatsAppClient("test"), NLPService(), db_session)

        issuer_id = handler.invoice_processor._resolve_issuer_id("+2348012345678")
        assert issuer_id == business_user.id

    def test_resolve_business_by_normalized_phone(self, business_user, db_session):
        """Test business lookup without + prefix"""
        handler = WhatsAppHandler(WhatsAppClient("test"), NLPService(), db_session)

        issuer_id = handler.invoice_processor._resolve_issuer_id("2348012345678")
        assert issuer_id == business_user.id

    def test_resolve_business_returns_none_for_unknown(self, db_session):
        """Test business lookup returns None for unknown number"""
        handler = WhatsAppHandler(WhatsAppClient("test"), NLPService(), db_session)

        issuer_id = handler.invoice_processor._resolve_issuer_id("+2349999999999")
        assert issuer_id is None
