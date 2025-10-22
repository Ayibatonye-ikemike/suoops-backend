# 🎙️ SuoPay Voice Bot Implementation Plan

## Current State ✅

**What Works:**
- ✅ WhatsApp text-based invoice creation
- ✅ NLP parsing of text commands
- ✅ Invoice creation and payment flow
- ✅ Customer notifications via WhatsApp

**What's Missing:**
- ❌ Voice call support (no voice bot)
- ❌ Voice note transcription
- ❌ Interactive voice response (IVR)
- ❌ Speech-to-text for invoice creation

---

## 🎯 Voice Bot Options

### Option 1: WhatsApp Voice Notes (RECOMMENDED - Quick Win)
**Timeline: 1-2 weeks**

Convert voice notes sent via WhatsApp into invoice commands.

#### Advantages:
- ✅ Users already have WhatsApp
- ✅ No new app or phone number needed
- ✅ Works with existing webhook infrastructure
- ✅ Lower cost (WhatsApp API only)
- ✅ Easier to implement

#### Flow:
```
1. User sends voice note to SuoPay WhatsApp
2. WhatsApp webhook delivers audio file URL
3. Download audio file (AAC/OGG format)
4. Transcribe using speech-to-text API
5. Pass transcript to existing NLPService
6. Create invoice and send confirmation
```

#### Technology Stack:
- **Speech-to-Text**: OpenAI Whisper API (most accurate for Nigerian English)
  - Alternative: Google Cloud Speech-to-Text
  - Alternative: AssemblyAI (good for accents)
- **Audio Processing**: FFmpeg (convert WhatsApp audio formats)
- **Storage**: S3 for temporary audio files

#### Cost Estimate:
- OpenAI Whisper: $0.006 per minute (~₦10 per voice note)
- Storage: Negligible (delete after transcription)
- **Total: ~₦10-20 per voice invoice**

---

### Option 2: Phone Call Bot (IVR System)
**Timeline: 3-4 weeks**

Dedicated phone number users can call to create invoices via voice.

#### Advantages:
- ✅ Works for users without smartphones
- ✅ More professional for some use cases
- ✅ Can handle complex multi-step flows
- ✅ No WhatsApp account required

#### Disadvantages:
- ❌ Higher cost (Twilio/Vonage charges)
- ❌ Requires dedicated phone number
- ❌ More complex infrastructure
- ❌ Call quality issues in Nigeria

#### Flow:
```
1. User calls SuoPay hotline: +234-XXX-XXXX
2. IVR greets: "Welcome to SuoPay. Say the customer name..."
3. Record customer name → transcribe
4. "What's the amount?"
5. Record amount → transcribe & validate
6. "What's the description?"
7. Record description → transcribe
8. Confirm details via speech
9. Create invoice and send SMS confirmation
```

#### Technology Stack:
- **Voice Infrastructure**: Twilio Voice API
  - Alternative: Vonage Voice API
  - Alternative: Africa's Talking Voice (best for Nigeria)
- **Speech Recognition**: Twilio + Whisper hybrid
- **Text-to-Speech**: Twilio Voices (Nigerian English)

#### Cost Estimate (Africa's Talking):
- Phone number: ₦2,000/month
- Incoming calls: ₦15/minute
- Outgoing SMS: ₦4/SMS
- **Total: ₦20-50 per call depending on length**

---

### Option 3: Hybrid Approach (BEST LONG-TERM)
**Timeline: 4-6 weeks**

Support both WhatsApp voice notes AND phone calls.

#### Benefits:
- ✅ Maximum accessibility
- ✅ Users choose their preferred channel
- ✅ Fallback if one channel fails
- ✅ Cover both smartphone and feature phone users

---

## 📋 Recommended Implementation: WhatsApp Voice Notes

### Phase 1: Infrastructure Setup (Week 1)

#### 1.1 Add Speech-to-Text Service
```python
# app/services/speech_service.py

import httpx
import tempfile
from pathlib import Path
from app.core.config import settings
from app.core.logger import logger

class SpeechService:
    """Handle speech-to-text transcription."""
    
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = "https://api.openai.com/v1/audio/transcriptions"
    
    async def transcribe_audio(self, audio_url: str, language: str = "en") -> str:
        """
        Download audio from WhatsApp and transcribe to text.
        
        Args:
            audio_url: WhatsApp media URL
            language: Language code (default: en for English)
        
        Returns:
            Transcribed text
        """
        try:
            # Download audio file from WhatsApp
            audio_bytes = await self._download_whatsapp_audio(audio_url)
            
            # Convert to supported format if needed
            audio_file = await self._prepare_audio(audio_bytes)
            
            # Call Whisper API
            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {
                    "file": ("audio.mp3", audio_file, "audio/mpeg"),
                    "model": (None, "whisper-1"),
                    "language": (None, language),
                }
                headers = {"Authorization": f"Bearer {self.api_key}"}
                
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    files=files
                )
                response.raise_for_status()
                
                result = response.json()
                transcript = result.get("text", "")
                
                logger.info(f"Transcribed audio: {transcript[:100]}...")
                return transcript
        
        except Exception as e:
            logger.error(f"Speech transcription failed: {e}")
            raise
    
    async def _download_whatsapp_audio(self, media_url: str) -> bytes:
        """Download audio file from WhatsApp Cloud API."""
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"
            }
            response = await client.get(media_url, headers=headers)
            response.raise_for_status()
            return response.content
    
    async def _prepare_audio(self, audio_bytes: bytes) -> bytes:
        """Convert audio to format compatible with Whisper API."""
        # WhatsApp sends OGG/AAC, Whisper accepts multiple formats
        # For production, use FFmpeg to convert to MP3
        # For now, return as-is (Whisper handles most formats)
        return audio_bytes
    
    def detect_language(self, text: str) -> str:
        """
        Detect if transcription is in English, Yoruba, Igbo, Hausa, or Pidgin.
        Returns language code for better parsing.
        """
        # Simple heuristic - expand with langdetect library
        common_pidgin = ["wetin", "how far", "abeg", "oga", "bros"]
        if any(word in text.lower() for word in common_pidgin):
            return "pidgin"
        return "en"
```

#### 1.2 Update WhatsApp Webhook Handler
```python
# app/bot/whatsapp_adapter.py

from app.services.speech_service import SpeechService

class WhatsAppHandler:
    def __init__(self, db: Session):
        self.db = db
        self.nlp = NLPService()
        self.speech = SpeechService()  # NEW
        self.client = WhatsAppClient()
    
    async def handle_message(self, message: dict):
        """Handle incoming WhatsApp message (text or voice)."""
        msg_type = message.get("type")
        from_number = message.get("from")
        
        if msg_type == "text":
            # Existing text handling
            text = message.get("text", {}).get("body", "")
            await self._process_text_command(from_number, text)
        
        elif msg_type == "audio":  # NEW - Voice note handling
            # WhatsApp voice note received
            audio = message.get("audio", {})
            media_id = audio.get("id")
            
            await self._process_voice_command(from_number, media_id)
        
        else:
            await self.client.send_message(
                from_number,
                "Sorry, I only understand text messages and voice notes for now."
            )
    
    async def _process_voice_command(self, phone: str, media_id: str):
        """Transcribe voice note and create invoice."""
        try:
            # Send "processing" message
            await self.client.send_message(
                phone,
                "🎙️ Processing your voice message..."
            )
            
            # Get media URL from WhatsApp
            media_url = await self.client.get_media_url(media_id)
            
            # Transcribe audio to text
            transcript = await self.speech.transcribe_audio(media_url)
            
            # Log for debugging
            logger.info(f"Voice transcript from {phone}: {transcript}")
            
            # Process transcript as normal text command
            await self._process_text_command(phone, transcript)
        
        except Exception as e:
            logger.error(f"Voice processing error: {e}")
            await self.client.send_message(
                phone,
                "❌ Sorry, I couldn't understand that voice message. "
                "Please try again or send a text message."
            )
```

#### 1.3 Update WhatsApp Client
```python
# app/bot/whatsapp_adapter.py (continued)

class WhatsAppClient:
    async def get_media_url(self, media_id: str) -> str:
        """
        Retrieve media URL from WhatsApp Cloud API.
        
        Args:
            media_id: The media ID from webhook
        
        Returns:
            Direct URL to download the audio file
        """
        url = f"https://graph.facebook.com/v21.0/{media_id}"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            media_url = data.get("url")
            
            return media_url
```

#### 1.4 Environment Variables
```bash
# .env additions

# OpenAI Whisper API
OPENAI_API_KEY=sk-proj-...

# Alternative: Google Cloud Speech-to-Text
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Alternative: AssemblyAI
# ASSEMBLYAI_API_KEY=...
```

### Phase 2: Enhanced NLP for Speech (Week 2)

Speech transcriptions often have issues that text doesn't:
- Filler words: "uhh", "umm", "like"
- Pronunciation errors: "fifty thousand" → "50,000"
- Missing punctuation
- Run-on sentences

#### 2.1 Enhanced NLP Preprocessing
```python
# app/bot/nlp_service.py

import re
from num2words import words2nums  # pip install num2words

class NLPService:
    def __init__(self):
        self.filler_words = ["uhh", "umm", "like", "you know", "so", "basically"]
    
    def parse_invoice_from_speech(self, transcript: str) -> dict:
        """
        Parse invoice from speech transcript.
        Handles number words and filler words.
        """
        # Clean up transcript
        cleaned = self._clean_speech_transcript(transcript)
        
        # Use existing parse_invoice logic
        return self.parse_invoice(cleaned)
    
    def _clean_speech_transcript(self, text: str) -> str:
        """Remove filler words and normalize speech patterns."""
        # Remove filler words
        for filler in self.filler_words:
            text = re.sub(rf"\b{filler}\b", "", text, flags=re.IGNORECASE)
        
        # Convert number words to digits
        text = self._convert_number_words(text)
        
        # Normalize spacing
        text = re.sub(r"\s+", " ", text).strip()
        
        return text
    
    def _convert_number_words(self, text: str) -> str:
        """
        Convert spoken numbers to digits.
        
        Examples:
        - "fifty thousand" → "50000"
        - "one hundred and twenty five" → "125"
        - "five thousand naira" → "5000 naira"
        """
        # Pattern for common number phrases
        patterns = {
            r"fifty thousand": "50000",
            r"one hundred thousand": "100000",
            r"two hundred thousand": "200000",
            r"twenty five thousand": "25000",
            r"thirty thousand": "30000",
            r"forty thousand": "40000",
            r"sixty thousand": "60000",
            r"seventy thousand": "70000",
            r"eighty thousand": "80000",
            r"ninety thousand": "90000",
            r"one million": "1000000",
        }
        
        for phrase, number in patterns.items():
            text = re.sub(phrase, number, text, flags=re.IGNORECASE)
        
        return text
```

### Phase 3: User Experience Enhancements

#### 3.1 Voice Command Confirmation
```python
# After transcription, show what was understood
await self.client.send_message(
    phone,
    f"📝 I heard: \"{transcript}\"\n\n"
    f"Creating invoice for {customer_name}...",
)
```

#### 3.2 Error Handling for Unclear Audio
```python
# If transcript is too short or unclear
if len(transcript.split()) < 3:
    await self.client.send_message(
        phone,
        "⚠️ Your voice message was too short or unclear.\n\n"
        "Please try again and speak clearly:\n"
        "\"Invoice [Customer Name] [Amount] for [Description]\""
    )
    return
```

#### 3.3 Help Command
```python
# app/bot/whatsapp_adapter.py

if text.lower() in ["help", "voice help", "how to use voice"]:
    await self.client.send_message(
        phone,
        "🎙️ *Voice Invoice Creation*\n\n"
        "You can now send voice notes to create invoices!\n\n"
        "*How to use:*\n"
        "1. Tap and hold the microphone button\n"
        "2. Speak clearly:\n"
        "   \"Invoice John Doe fifty thousand naira for website design\"\n"
        "3. Release and send\n\n"
        "*Tips:*\n"
        "- Speak clearly and not too fast\n"
        "- Say amounts in full: \"fifty thousand\" not \"50k\"\n"
        "- Include customer name, amount, and description\n\n"
        "*Example:*\n"
        "\"Create invoice for Mary Johnson, twenty five thousand naira, "
        "for logo design, due next week\""
    )
```

### Phase 4: Testing & Optimization

#### 4.1 Test Cases
```python
# tests/test_voice_invoice.py

import pytest
from app.services.speech_service import SpeechService
from app.bot.nlp_service import NLPService

@pytest.mark.asyncio
async def test_voice_transcription():
    """Test audio transcription with sample file."""
    service = SpeechService()
    # Upload sample voice note to test storage
    audio_url = "https://example.com/test-audio.ogg"
    transcript = await service.transcribe_audio(audio_url)
    assert len(transcript) > 0

def test_speech_number_parsing():
    """Test number word conversion."""
    nlp = NLPService()
    
    text = "invoice John fifty thousand naira for consulting"
    cleaned = nlp._clean_speech_transcript(text)
    
    assert "50000" in cleaned
    assert "fifty thousand" not in cleaned

def test_filler_word_removal():
    """Test filler word cleanup."""
    nlp = NLPService()
    
    text = "uhh invoice umm like John Doe you know fifty thousand"
    cleaned = nlp._clean_speech_transcript(text)
    
    assert "uhh" not in cleaned
    assert "umm" not in cleaned
    assert "John Doe" in cleaned
```

#### 4.2 Monitoring & Metrics
```python
# app/metrics.py

voice_transcriptions_total = Counter(
    "voice_transcriptions_total",
    "Total voice notes transcribed",
    ["status"]  # success, failed
)

voice_transcription_duration = Histogram(
    "voice_transcription_duration_seconds",
    "Time to transcribe audio",
)

voice_invoice_created = Counter(
    "voice_invoice_created_total",
    "Invoices created from voice commands"
)
```

---

## 💰 Cost Analysis

### WhatsApp Voice Notes Approach

**Fixed Costs:**
- OpenAI Whisper API: $0.006 per minute
- WhatsApp Business API: Free (pay-as-you-go)
- Storage (S3): ~$0.001 per audio file

**Per-Invoice Cost:**
- Average voice note: 30 seconds = $0.003 (~₦5)
- WhatsApp message delivery: Free
- **Total: ~₦5-10 per voice invoice**

**At Scale (1000 voice invoices/month):**
- Transcription: $3 (~₦5,000)
- Storage: $1 (~₦1,600)
- **Total: ~₦6,600/month**

### Phone Call IVR Approach (for comparison)

**Fixed Costs:**
- Africa's Talking phone number: ₦2,000/month
- SMS delivery: ₦4/SMS

**Per-Invoice Cost:**
- Average call duration: 2 minutes = ₦30
- Confirmation SMS: ₦4
- **Total: ~₦34 per call invoice**

**At Scale (1000 calls/month):**
- Phone number: ₦2,000
- Call charges: ₦30,000
- SMS: ₦4,000
- **Total: ~₦36,000/month**

### Recommendation: Start with WhatsApp Voice Notes
- **6x cheaper** than phone calls
- **No new infrastructure** required
- **Faster to implement** (1-2 weeks vs 4 weeks)
- **Better UX** (users already on WhatsApp)

---

## 🚀 Implementation Timeline

### Week 1: Core Implementation
- Day 1-2: Set up OpenAI Whisper API integration
- Day 3: Update WhatsApp webhook for audio messages
- Day 4: Enhanced NLP for speech preprocessing
- Day 5: Testing with sample voice notes

### Week 2: Polish & Launch
- Day 1-2: Error handling and confirmations
- Day 3: User guide and help commands
- Day 4: Load testing and optimization
- Day 5: Deploy and monitor

### Week 3-4 (Optional): Phone Call IVR
- If demand exists for phone calls
- Integrate Africa's Talking Voice API
- Build IVR flow with Twilio/Vonage

---

## 📊 Success Metrics

### Key Performance Indicators:
- **Transcription Accuracy**: >90% word error rate
- **Invoice Creation Success**: >85% of voice notes → invoices
- **User Adoption**: 20% of invoices via voice within 3 months
- **Processing Time**: <10 seconds from voice note to invoice
- **User Satisfaction**: >4.5/5 stars for voice feature

### Monitoring:
```python
# Track these metrics:
- voice_transcriptions_total (success vs failed)
- voice_transcription_accuracy (manual review sample)
- voice_invoice_success_rate
- voice_processing_duration_seconds
- voice_feature_adoption_rate
```

---

## ✅ Next Steps

**Immediate (This Week):**
1. ✅ Approve WhatsApp voice note approach
2. ✅ Sign up for OpenAI API key
3. ✅ Test Whisper API with sample Nigerian English audio
4. ✅ Update WhatsApp webhook to accept audio messages

**Phase 1 (Week 1):**
- Implement SpeechService
- Update WhatsApp handler for voice notes
- Add enhanced NLP preprocessing
- Deploy to staging

**Phase 2 (Week 2):**
- User testing with real voice notes
- Optimize transcription accuracy
- Add confirmation messages
- Deploy to production

**Future Considerations:**
- Multi-language support (Yoruba, Igbo, Hausa, Pidgin)
- Phone call IVR if demand exists
- Voice analytics dashboard
- Accent training for better accuracy

---

## 🎤 Sample User Flows

### Flow 1: Quick Invoice via Voice
```
1. User opens WhatsApp
2. Holds microphone button
3. Says: "Invoice Jane Smith fifty thousand naira for website hosting due next week"
4. Releases button and sends
5. Receives: "🎙️ Processing your voice message..."
6. Receives: "📝 I heard: Invoice Jane Smith 50000 naira..."
7. Receives: "✅ Invoice #INV-001 created for Jane Smith - ₦50,000"
8. Jane receives invoice link
```

### Flow 2: Voice Note with Errors
```
1. User sends unclear voice note
2. Receives: "⚠️ I couldn't quite understand that. I heard: '...mumble mumble...'"
3. Receives: "Please try again or send a text message"
4. User sends clearer voice note
5. Invoice created successfully
```

---

**Ready to implement voice notes?** 🚀 This will give your users the fastest way to create invoices while driving!
