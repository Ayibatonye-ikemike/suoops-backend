"""
Tests for voice note transcription and speech processing.

Validates SRP: Each service has focused tests.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.services.speech_service import SpeechService
from app.bot.nlp_service import NLPService


class TestSpeechService:
    """Test speech transcription service."""

    @pytest.mark.asyncio
    async def test_transcribe_audio_success(self):
        """Test successful audio transcription."""
        service = SpeechService()
        service.api_key = "test-key"
        
        mock_response = Mock()
        mock_response.json.return_value = {"text": "Invoice John fifty thousand naira"}
        mock_response.raise_for_status = Mock()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            result = await service.transcribe_audio(b"fake-audio-bytes")
            
            assert result == "Invoice John fifty thousand naira"

    @pytest.mark.asyncio
    async def test_transcribe_audio_no_api_key(self):
        """Test transcription fails without API key."""
        service = SpeechService()
        service.api_key = None
        
        with pytest.raises(ValueError, match="OPENAI_API_KEY not configured"):
            await service.transcribe_audio(b"fake-audio-bytes")


class TestNLPServiceSpeech:
    """Test NLP service speech-specific features."""

    def test_clean_speech_text_removes_fillers(self):
        """Test filler word removal."""
        nlp = NLPService()
        
        text = "uhh invoice umm like John Doe you know fifty thousand"
        cleaned = nlp._clean_speech_text(text)
        
        assert "uhh" not in cleaned.lower()
        assert "umm" not in cleaned.lower()
        assert "like" not in cleaned.lower()
        assert "John Doe" in cleaned

    def test_clean_speech_text_converts_numbers(self):
        """Test spoken number conversion."""
        nlp = NLPService()
        
        test_cases = [
            ("invoice John fifty thousand naira", "50000"),
            ("twenty five thousand for design", "25000"),
            ("one hundred thousand due tomorrow", "100000"),
        ]
        
        for text, expected_number in test_cases:
            cleaned = nlp._clean_speech_text(text)
            assert expected_number in cleaned

    def test_parse_text_with_speech_flag(self):
        """Test parsing with speech cleaning enabled."""
        nlp = NLPService()
        
        text = "uhh invoice umm Jane fifty thousand naira for logo"
        result = nlp.parse_text(text, is_speech=True)
        
        assert result.intent == "create_invoice"
        assert result.entities["customer_name"] == "Jane"
        assert result.entities["amount"] == 50000

    def test_parse_text_without_speech_flag(self):
        """Test parsing without speech cleaning."""
        nlp = NLPService()
        
        text = "invoice Jane 50000 naira for logo"
        result = nlp.parse_text(text, is_speech=False)
        
        assert result.intent == "create_invoice"
        assert result.entities["customer_name"] == "Jane"


class TestWhatsAppVoiceIntegration:
    """Integration tests for voice note handling."""

    @pytest.mark.asyncio
    async def test_voice_note_too_short(self):
        """Test handling of very short voice notes."""
        from app.bot.whatsapp_adapter import WhatsAppHandler, WhatsAppClient
        from app.bot.nlp_service import NLPService
        
        mock_client = Mock(spec=WhatsAppClient)
        mock_client.send_text = Mock()
        mock_client.get_media_url = AsyncMock(return_value="https://example.com/audio.ogg")
        mock_client.download_media = AsyncMock(return_value=b"audio")
        
        nlp = NLPService()
        invoice_service = Mock()
        
        handler = WhatsAppHandler(mock_client, nlp, invoice_service)
        
        # Mock speech service to return very short transcript
        with patch.object(handler, "speech_service") as mock_speech:
            mock_speech.transcribe_audio = AsyncMock(return_value="hi")
            
            await handler._handle_audio_message("+1234567890", "media123", {})
            
            # Should send error message about short transcript
            assert mock_client.send_text.call_count >= 2
            error_call = [call for call in mock_client.send_text.call_args_list 
                         if "too short" in str(call)]
            assert len(error_call) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
