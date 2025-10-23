"""
Test WhatsApp three-way flow: Business → Bot → Customer

This test validates the complete flow:
1. Business sends WhatsApp message to centralized bot
2. Bot identifies business by phone lookup
3. Bot extracts customer phone from message
4. Bot creates invoice with business credentials
5. Bot sends confirmation to business
6. Invoice delivered to customer
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
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
    """Create a business user with WhatsApp phone number"""
    user = User(
        email="mike@business.com",
        phone="+2348012345678",  # Matches sender in webhook payload
        hashed_password="hashed_test_password",
        business_name="Mike's Design Studio",
        paystack_secret="sk_test_abc123"
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

    @patch('app.bot.whatsapp_adapter.WhatsAppClient')
    def test_text_message_flow_complete(
        self, 
        mock_client_class, 
        business_user, 
        db_session,
        whatsapp_text_payload
    ):
        """
        Test complete flow for text message:
        1. Business sends text message
        2. Bot identifies business by phone
        3. Bot extracts customer phone
        4. Bot creates invoice
        5. Bot sends confirmation
        """
        from app.bot.whatsapp_adapter import WhatsAppHandler
        
        # Mock WhatsApp client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Process the webhook payload
        handler = WhatsAppHandler(db_session, "test_api_key")
        handler.handle_webhook(whatsapp_text_payload)
        
        # Verify bot sent confirmation message
        mock_client.send_text.assert_called()
        call_args = mock_client.send_text.call_args
        
        # Check confirmation was sent to business
        assert call_args[0][0] == "2348012345678"  # Business phone
        assert "Invoice created" in call_args[0][1] or "✓" in call_args[0][1]
        
        # Verify invoice was created in database
        from app.models.models import Invoice
        invoice = db_session.query(Invoice).filter(
            Invoice.issuer_id == business_user.id
        ).first()
        
        assert invoice is not None
        assert invoice.customer_name == "Jane Doe"
        assert invoice.customer_phone == "+2348087654321"
        assert invoice.total == 50000

    @patch('app.bot.whatsapp_adapter.WhatsAppClient')
    @patch('app.services.speech_service.SpeechService.transcribe_audio')
    def test_voice_note_flow_complete(
        self,
        mock_transcribe,
        mock_client_class,
        business_user,
        db_session,
        whatsapp_voice_payload
    ):
        """
        Test complete flow for voice note:
        1. Business sends voice note
        2. Bot transcribes audio (Whisper)
        3. Bot preprocesses speech
        4. Bot identifies business by phone
        5. Bot extracts customer phone
        6. Bot creates invoice
        """
        from app.bot.whatsapp_adapter import WhatsAppHandler
        
        # Mock transcription result
        mock_transcribe.return_value = (
            "invoice jane doe zero eight zero eight seven six five four three two one "
            "fifty thousand naira for logo design"
        )
        
        # Mock WhatsApp client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.download_audio.return_value = b"fake_audio_data"
        
        # Process the webhook payload
        handler = WhatsAppHandler(db_session, "test_api_key")
        handler.handle_webhook(whatsapp_voice_payload)
        
        # Verify transcription was called
        mock_transcribe.assert_called_once()
        
        # Verify bot sent confirmation
        mock_client.send_text.assert_called()
        call_args = mock_client.send_text.call_args
        assert call_args[0][0] == "2348012345678"  # Business phone
        
        # Verify invoice was created
        from app.models.models import Invoice
        invoice = db_session.query(Invoice).filter(
            Invoice.issuer_id == business_user.id
        ).first()
        
        assert invoice is not None
        assert invoice.customer_phone == "+2348087654321"

    @patch('app.bot.whatsapp_adapter.WhatsAppClient')
    def test_unregistered_business_rejected(
        self,
        mock_client_class,
        db_session,
        whatsapp_text_payload
    ):
        """Test that unregistered phone numbers get helpful error"""
        from app.bot.whatsapp_adapter import WhatsAppHandler
        
        # Mock WhatsApp client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Process webhook (no business user registered)
        handler = WhatsAppHandler(db_session, "test_api_key")
        handler.handle_webhook(whatsapp_text_payload)
        
        # Verify error message was sent
        mock_client.send_text.assert_called()
        call_args = mock_client.send_text.call_args
        assert "Unable to identify your business account" in call_args[0][1]
        assert "suopay.io/dashboard/settings" in call_args[0][1]

    @patch('app.bot.whatsapp_adapter.WhatsAppClient')
    def test_missing_customer_phone_rejected(
        self,
        mock_client_class,
        business_user,
        db_session
    ):
        """Test that messages without customer phone get helpful error"""
        from app.bot.whatsapp_adapter import WhatsAppHandler
        
        # Mock WhatsApp client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Payload with no phone number in text
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
                                            "body": "Invoice Jane Doe 50000 for logo"  # Missing phone!
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
        
        # Process webhook
        handler = WhatsAppHandler(db_session, "test_api_key")
        handler.handle_webhook(payload)
        
        # Verify error message was sent
        mock_client.send_text.assert_called()
        call_args = mock_client.send_text.call_args
        assert "⚠️" in call_args[0][1]
        assert "customer's phone number" in call_args[0][1]
        assert "Example:" in call_args[0][1]


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
        from app.bot.whatsapp_adapter import WhatsAppHandler
        
        handler = WhatsAppHandler(db_session, "test_api_key")
        
        # Test exact match
        issuer_id = handler._resolve_issuer_id("+2348012345678")
        assert issuer_id == business_user.id

    def test_resolve_business_by_normalized_phone(self, business_user, db_session):
        """Test business lookup without + prefix"""
        from app.bot.whatsapp_adapter import WhatsAppHandler
        
        handler = WhatsAppHandler(db_session, "test_api_key")
        
        # Test without + prefix
        issuer_id = handler._resolve_issuer_id("2348012345678")
        assert issuer_id == business_user.id

    def test_resolve_business_returns_none_for_unknown(self, db_session):
        """Test business lookup returns None for unknown number"""
        from app.bot.whatsapp_adapter import WhatsAppHandler
        
        handler = WhatsAppHandler(db_session, "test_api_key")
        
        issuer_id = handler._resolve_issuer_id("+2349999999999")
        assert issuer_id is None
