from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ParseResult:
    intent: str
    entities: dict[str, object]
    confidence: float = 0.9


class NLPService:
    """
    Natural language processing for invoice commands.
    
    Single Responsibility: Parse text into structured invoice data.
    """
    
    AMOUNT_PATTERN = re.compile(r"(?:₦|ngn)?\s?([0-9]{3,}(?:,[0-9]{3})*|[0-9]+)(?:\.[0-9]{1,2})?")
    
    # Filler words to remove from speech transcripts
    FILLER_WORDS = ["uhh", "umm", "like", "you know", "so", "basically", "actually"]
    
    # Common spoken number patterns (Nigerian English)
    NUMBER_WORDS = {
        r"\bfifty thousand\b": "50000",
        r"\bone hundred thousand\b": "100000",
        r"\btwo hundred thousand\b": "200000",
        r"\btwenty[- ]?five thousand\b": "25000",
        r"\bthirty thousand\b": "30000",
        r"\bforty thousand\b": "40000",
        r"\bsixty thousand\b": "60000",
        r"\bseventy thousand\b": "70000",
        r"\beighty thousand\b": "80000",
        r"\bninety thousand\b": "90000",
        r"\bone million\b": "1000000",
        r"\btwo million\b": "2000000",
        r"\bfive hundred\b": "500",
        r"\bone thousand\b": "1000",
        r"\bfive thousand\b": "5000",
        r"\bten thousand\b": "10000",
    }

    def parse_text(self, text: str, is_speech: bool = False) -> ParseResult:
        """
        Parse text command into structured data.
        
        Args:
            text: User input text
            is_speech: Whether text is from speech transcription
        
        Returns:
            ParseResult with intent and extracted entities
        """
        # Clean speech artifacts if needed
        if is_speech:
            text = self._clean_speech_text(text)
        
        lower = text.lower()
        if "invoice" in lower:
            entities = self._extract_invoice(lower)
            return ParseResult(intent="create_invoice", entities=entities)
        return ParseResult(intent="unknown", entities={}, confidence=0.2)
    
    def _clean_speech_text(self, text: str) -> str:
        """
        Clean speech transcription artifacts.
        
        Removes filler words and converts number words to digits.
        DRY: Single place for all speech cleaning logic.
        """
        # Remove filler words
        for filler in self.FILLER_WORDS:
            text = re.sub(rf"\b{filler}\b", "", text, flags=re.IGNORECASE)
        
        # Convert spoken numbers to digits
        for pattern, number in self.NUMBER_WORDS.items():
            text = re.sub(pattern, number, text, flags=re.IGNORECASE)
        
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        
        return text

    def _extract_invoice(self, text: str) -> dict[str, object]:
        # naive parse: Invoice <name> <amount>
        tokens = text.split()
        name = tokens[1] if len(tokens) > 1 else "Customer"
        amount_match = self.AMOUNT_PATTERN.search(text)
        amount_raw = amount_match.group(1).replace(",", "") if amount_match else "0"
        due = None
        if "tomorrow" in text:
            due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
        return {
            "customer_name": name.capitalize(),
            "amount": Decimal(amount_raw),
            "due_date": due,
            "customer_phone": None,
        }
