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
    
    # Nigerian phone number patterns
    # Matches: +2348012345678, 2348012345678, 08012345678, 8012345678
    PHONE_PATTERN = re.compile(r"(\+?234[7-9]\d{9}|\+?[7-9]\d{9}|0[7-9]\d{9})")
    
    # Email pattern
    # Matches: user@example.com, name.surname@company.co.uk
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    
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

    DIGIT_WORDS = {
        "zero": "0",
        "oh": "0",
        "o": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
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

        # Convert sequences of digit words (e.g. "zero eight") into numeric strings
        tokens = []
        digit_buffer: list[str] = []
        for raw_token in text.split():
            token_lower = raw_token.lower()
            if token_lower in self.DIGIT_WORDS:
                digit_buffer.append(self.DIGIT_WORDS[token_lower])
                continue
            if digit_buffer:
                tokens.append("".join(digit_buffer))
                digit_buffer = []
            tokens.append(raw_token)
        if digit_buffer:
            tokens.append("".join(digit_buffer))

        text = " ".join(tokens)
        
        return text
    
    def _extract_phone(self, text: str) -> str | None:
        """
        Extract Nigerian phone number from text.
        
        Returns normalized phone number with +234 prefix or None if not found.
        
        Examples:
            "+2348012345678" → "+2348012345678"
            "2348012345678"  → "+2348012345678"
            "08012345678"    → "+2348012345678"
            "8012345678"     → "+2348012345678"
        """
        match = self.PHONE_PATTERN.search(text)
        if not match:
            return None
        
        phone = match.group(1)
        
        # Normalize to international format
        if phone.startswith('+234'):
            return phone
        elif phone.startswith('234'):
            return '+' + phone
        elif phone.startswith('0'):
            return '+234' + phone[1:]  # Remove leading 0
        else:
            return '+234' + phone  # Add country code
    
    def _extract_email(self, text: str) -> str | None:
        """
        Extract email address from text.
        
        Returns email address or None if not found.
        
        Examples:
            "jane@example.com" → "jane@example.com"
            "Send to john.doe@company.co.uk" → "john.doe@company.co.uk"
        """
        match = self.EMAIL_PATTERN.search(text)
        return match.group(0).lower() if match else None
    
    def _extract_invoice(self, text: str) -> dict[str, object]:
        """
        Extract invoice data including support for multiple items.
        
        Supported formats:
            Single item:
                "invoice Joy 12000 for wigs"
                "invoice 07065730703 12000 wigs"
            
            Multiple items (comma or space separated):
                "invoice 07065730703 wig 1000, shoe 3000"
                "invoice 07065730703 wig 1000 shoe 3000 bag 5000"
                "invoice Joy 07065730703 wigs 12000, shoes 5000"
        """
        tokens = text.split()
        name = tokens[1] if len(tokens) > 1 else "Customer"
        
        # Extract phone number first so we can avoid treating it as amount
        phone = self._extract_phone(text)
        
        # Extract email address
        email = self._extract_email(text)

        # Build a set of phone-related digit strings to skip
        phone_variants: set[str] = set()
        if phone:
            phone_digits = phone.replace("+", "")
            phone_variants.add(phone_digits)
            phone_variants.add(phone_digits.lstrip("234"))
            if phone_digits.startswith("234"):
                phone_variants.add("0" + phone_digits[3:])

        # Try to extract multiple items using pattern: <item_name> <amount>
        # Supports: "wig 1000, shoe 3000" or "wig 1000 shoe 3000"
        lines = self._extract_line_items(text, phone_variants)
        
        # Calculate total amount from all items
        if lines:
            total_amount = sum(Decimal(str(line["unit_price"])) * line.get("quantity", 1) for line in lines)
        else:
            # Fallback: single amount extraction for backward compatibility
            amount_raw = "0"
            for match in self.AMOUNT_PATTERN.finditer(text):
                candidate = match.group(1).replace(",", "")
                if candidate in phone_variants:
                    continue
                amount_raw = candidate
                break
            total_amount = Decimal(amount_raw)
            
            # Create a single line item with description
            description = self._extract_description(text)
            lines = [{"description": description, "quantity": 1, "unit_price": total_amount}]
        
        # Extract due date
        due = None
        if "tomorrow" in text:
            due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
        
        # If name looks like a phone number, use a default name
        if name and name.replace("+", "").replace("-", "").isdigit():
            name = "Customer"
        
        return {
            "customer_name": name.capitalize(),
            "amount": total_amount,
            "due_date": due,
            "customer_phone": phone,
            "customer_email": email,
            "lines": lines,
        }
    
    def _extract_line_items(self, text: str, phone_variants: set[str]) -> list[dict[str, object]]:
        """
        Extract multiple line items from text.
        
        Supports two patterns:
            1. Amount first: "1000 wig, 2000 shoe, 4000 belt"
            2. Item first: "wig 1000, shoe 2000" (fallback)
        
        Examples:
            "1000 wig, 2000 shoe" → [{"description": "Wig", "unit_price": 1000}, {"description": "Shoe", "unit_price": 2000}]
            "wig 1000, shoe 2000" → [{"description": "Wig", "unit_price": 1000}, {"description": "Shoe", "unit_price": 2000}]
        """
        lines = []
        
        # Remove common prefixes to focus on item data
        clean_text = text.lower()
        
        # Remove "invoice" and customer name (first word after invoice)
        clean_text = re.sub(r"^invoice\s+[a-zA-Z]+\s*", "", clean_text)
        
        for word in ["for", "due", "tomorrow", "today", "next week"]:
            clean_text = clean_text.replace(word, " ")
        
        # Remove phone number from text
        for variant in phone_variants:
            clean_text = clean_text.replace(variant.lower(), " ")
        
        # Also remove phone patterns directly
        clean_text = self.PHONE_PATTERN.sub(" ", clean_text)
        
        # Remove email from text
        clean_text = self.EMAIL_PATTERN.sub(" ", clean_text)
        
        # Split by comma to get individual items
        # "1000 wig, 2000 shoe, 4000 belt" → ["1000 wig", "2000 shoe", "4000 belt"]
        parts = [p.strip() for p in clean_text.split(",") if p.strip()]
        
        for part in parts:
            tokens = part.split()
            if len(tokens) < 2:
                continue
            
            # Try pattern 1: <amount> <item_name>
            # e.g., "1000 wig" or "2000 running shoes"
            first_token = tokens[0].replace(",", "")
            if first_token.isdigit() and len(first_token) >= 3:
                if first_token not in phone_variants:
                    item_name = " ".join(tokens[1:]).strip()
                    if item_name and not item_name.isdigit():
                        lines.append({
                            "description": item_name.capitalize(),
                            "quantity": 1,
                            "unit_price": Decimal(first_token),
                        })
                        continue
            
            # Try pattern 2: <item_name> <amount>
            # e.g., "wig 1000" or "running shoes 2000"
            last_token = tokens[-1].replace(",", "")
            if last_token.isdigit() and len(last_token) >= 3:
                if last_token not in phone_variants:
                    item_name = " ".join(tokens[:-1]).strip()
                    if item_name and not item_name[0].isdigit():
                        lines.append({
                            "description": item_name.capitalize(),
                            "quantity": 1,
                            "unit_price": Decimal(last_token),
                        })
        
        return lines
    
    def _extract_description(self, text: str) -> str:
        """Extract item description from text (for single-item invoices)."""
        # Look for "for <description>" pattern
        for_match = re.search(r"\bfor\s+([a-zA-Z][a-zA-Z\s]+?)(?:\s+due|\s*$)", text, re.IGNORECASE)
        if for_match:
            return for_match.group(1).strip().capitalize()
        
        # Default description
        return "Item"
