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
    # Detect USD-prefixed amounts: $50, $1,200.50, USD 500, usd500
    USD_AMOUNT_PATTERN = re.compile(r"(?:\$|usd)\s?([0-9]{1,}(?:,[0-9]{3})*|[0-9]+)(?:\.[0-9]{1,2})?", re.IGNORECASE)
    
    # Phone number patterns - supports Nigerian and international formats
    # Nigerian: +2348012345678, 2348012345678, 08012345678, 8012345678
    # International: +1234567890, +447123456789, +33612345678, etc.
    NIGERIAN_PHONE_PATTERN = re.compile(r"(\+?234[7-9]\d{9}|\+?[7-9]\d{9}|0[7-9]\d{9})")
    INTL_PHONE_PATTERN = re.compile(r"(\+[1-9]\d{6,14})")
    # Combined pattern for extraction - Nigerian first (more specific), then international
    PHONE_PATTERN = re.compile(
        r"(\+?234[7-9]\d{9}|0[7-9]\d{9}|[7-9]\d{9}|\+[1-9]\d{6,14})"
    )
    
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
    
    # Common Nigerian names for smarter extraction
    COMMON_NAMES = {
        "joy", "ada", "mike", "john", "mary", "grace", "blessing", "favour",
        "chidi", "emeka", "ngozi", "chioma", "uche", "eze", "amara", "kemi",
        "tunde", "segun", "bola", "funke", "yemi", "femi", "bukky", "tobi",
        "dayo", "kunle", "sade", "wale", "ayo", "ola", "tola", "shade",
        "monica", "peter", "paul", "james", "david", "sarah", "ruth", "esther",
        "fatimah", "fatima", "aisha", "musa", "ibrahim", "yusuf", "abdullahi",
        "solomon", "daniel", "samuel", "joshua", "rachel", "rebecca", "hannah",
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
        Extract phone number from text - supports Nigerian and international formats.
        
        Returns normalized phone number with + prefix or None if not found.
        
        Handles:
            - Spaces in phone numbers: "0902018 0595" → "+2349020180595"
            - Standard formats: "08012345678" → "+2348012345678"
            - With country code: "2348012345678" → "+2348012345678"
        
        Nigerian Examples:
            "+2348012345678" → "+2348012345678"
            "2348012345678"  → "+2348012345678"
            "08012345678"    → "+2348012345678"
            "8012345678"     → "+2348012345678"
            "0902018 0595"   → "+2349020180595"
        
        International Examples:
            "+14155551234"   → "+14155551234" (US)
            "+447911123456"  → "+447911123456" (UK)
            "+33612345678"   → "+33612345678" (France)
        """
        # First try standard pattern
        match = self.PHONE_PATTERN.search(text)
        if match:
            phone = match.group(1)
        else:
            # Try to find phone with spaces: look for digit sequences that form a phone
            # Pattern: starts with 0 or +, followed by digits (possibly with spaces)
            # E.g., "0902018 0595" or "090 2018 0595"
            space_phone_pattern = re.compile(r"(0[789][\d\s]{8,12})")
            space_match = space_phone_pattern.search(text)
            if space_match:
                # Remove all spaces to get clean phone number
                phone = space_match.group(1).replace(" ", "")
            else:
                return None
        
        # If already has +, it's properly formatted
        if phone.startswith('+'):
            return phone
        
        # Check if it's a Nigerian number format
        if phone.startswith('234') and len(phone) == 13:
            return '+' + phone
        elif phone.startswith('0') and len(phone) == 11 and phone[1] in '789':
            return '+234' + phone[1:]  # Remove leading 0, add +234
        elif len(phone) == 10 and phone[0] in '789':
            return '+234' + phone  # Add +234 country code
        
        # For other international formats without +, return as-is with + prefix
        # This handles cases like "14155551234" → "+14155551234"
        return '+' + phone
    
    def _extract_name_from_text(self, text: str) -> str:
        """
        Extract customer name from text when format is non-standard.
        
        Handles cases like 'Invoice 500, Monica fish' where amount comes before name.
        Looks for known names or capitalized words that aren't amounts/items.
        
        Returns:
            Extracted name or 'Customer' as fallback.
        """
        # Remove 'invoice' prefix and split
        clean = re.sub(r"^invoice\s+", "", text.lower())
        tokens = clean.replace(",", " ").split()
        
        # First pass: look for known common names
        for token in tokens:
            if token in self.COMMON_NAMES:
                return token.capitalize()
        
        # Second pass: find first alphabetic token that's not a common item word
        item_words = {
            "wig", "hair", "braids", "gel", "shoe", "shoes", "shirt", "dress",
            "bag", "phone", "laptop", "service", "consulting", "design", "food",
            "fish", "rice", "item", "product", "goods", "delivery", "transport",
        }
        
        for token in tokens:
            # Skip if it's a number, phone-like, or common item word
            if token.isdigit():
                continue
            if token.replace("+", "").replace("-", "").isdigit():
                continue
            if token in item_words:
                continue
            if len(token) < 2:
                continue
            # Found a potential name
            if token.isalpha():
                return token.capitalize()
        
        return "Customer"
    
    # ---------- due-date helpers ----------
    _WEEKDAYS = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    _MONTHS = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    _DUE_IN_PATTERN = re.compile(
        r"(?:due\s+)?in\s+(\d{1,3})\s*(?:days?|d)", re.IGNORECASE
    )
    _DUE_WEEKDAY_PATTERN = re.compile(
        r"due\s+(?:next\s+)?(?:on\s+)?(" + "|".join(_WEEKDAYS) + r")",
        re.IGNORECASE,
    )
    _DUE_MONTH_DAY_PATTERN = re.compile(
        r"due\s+(?:on\s+)?(" + "|".join(_MONTHS) + r")\s+(\d{1,2})",
        re.IGNORECASE,
    )

    def _extract_due_date(self, text: str) -> dt.datetime | None:
        """Extract due date from natural language.

        Supported:
            "tomorrow"                 → +1 day
            "due in 7 days"            → +7 days
            "in 14 days"               → +14 days
            "due next week"            → +7 days
            "due friday" / "due fri"   → next occurrence of that weekday
            "due march 5"              → specific calendar date
        """
        text_lower = text.lower()
        now = dt.datetime.now(dt.timezone.utc)

        # "tomorrow"
        if "tomorrow" in text_lower:
            return now + dt.timedelta(days=1)

        # "due next week"
        if "next week" in text_lower:
            return now + dt.timedelta(days=7)

        # "due in 7 days" / "in 14d"
        m = self._DUE_IN_PATTERN.search(text_lower)
        if m:
            days = min(int(m.group(1)), 365)
            return now + dt.timedelta(days=days)

        # "due friday" / "due next monday"
        m = self._DUE_WEEKDAY_PATTERN.search(text_lower)
        if m:
            target_day = self._WEEKDAYS[m.group(1).lower()]
            days_ahead = (target_day - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # next occurrence, not today
            return now + dt.timedelta(days=days_ahead)

        # "due march 5" / "due jan 15"
        m = self._DUE_MONTH_DAY_PATTERN.search(text_lower)
        if m:
            month = self._MONTHS[m.group(1).lower()]
            day = int(m.group(2))
            year = now.year
            try:
                target = dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
                if target < now:
                    target = target.replace(year=year + 1)
                return target
            except ValueError:
                pass  # invalid day — fall through to None

        return None  # backend auto-defaults to 3 days

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
            Standard (name first):
                "invoice Joy 08012345678, 12000 wig"
                "invoice Joy 12000 wig"
            
            Alternate (amount first - common user mistake):
                "invoice 500, Monica fish"
                "invoice 12000 Joy wig"
            
            Multiple items (comma separated, amount before item):
                "invoice Joy 08012345678, 2000 boxers, 5000 hair"
                "invoice Joy 08012345678, 1000 wig, 2000 shoe, 4000 belt"
        """
        tokens = text.split()
        
        # Smart name extraction: check if second token looks like amount
        # If so, look for name elsewhere in the text
        name = "Customer"
        if len(tokens) > 1:
            second_token = tokens[1].replace(",", "").replace("₦", "").replace("ngn", "")
            if second_token.isdigit() and len(second_token) >= 3:
                # Amount came first - look for name after the comma or amount
                name = self._extract_name_from_text(text)
            else:
                # Standard format - name is second token
                name = tokens[1]
        
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
        
        # Extract due date — supports natural language
        due = self._extract_due_date(text)
        
        # If name looks like a phone number, use a default name
        if name and name.replace("+", "").replace("-", "").isdigit():
            name = "Customer"

        # Detect currency — check for USD markers ($, usd, dollar) in the text
        text_lower = text.lower()
        has_usd_marker = bool(self.USD_AMOUNT_PATTERN.search(text)) or "dollar" in text_lower
        currency = "USD" if has_usd_marker else "NGN"
        
        return {
            "customer_name": name.capitalize(),
            "amount": total_amount,
            "currency": currency,
            "due_date": due,
            "customer_phone": phone,
            "customer_email": email,
            "lines": lines,
        }
    
    def _extract_line_items(self, text: str, phone_variants: set[str]) -> list[dict[str, object]]:
        """
        Extract multiple line items from text.
        
        Supports formats:
            1. Amount first: "1000 wig, 2000 shoe, 4000 belt"
            2. Item first: "wig 1000, shoe 2000" (fallback)
            3. Comma-formatted amounts: "11,000 Design, 10,000 Printing"
            4. Space-separated items: "40,000 shoe 50,000 bag"
            5. Comma after amount: "40,000, shoe, 50,000 bag"
            6. Typo handling: "20,00" treated as "2000" (2 digits after comma)
        
        Examples:
            "1000 wig, 2000 shoe" →
                [{"description": "Wig", "unit_price": 1000}, {"description": "Shoe", "unit_price": 2000}]
            "40,000 shoe 50,000 bag" →
                [{"description": "Shoe", "unit_price": 40000}, {"description": "Bag", "unit_price": 50000}]
            "40,000, shoe, 50,000 bag" →
                [{"description": "Shoe", "unit_price": 40000}, {"description": "Bag", "unit_price": 50000}]
        """
        lines = []
        
        # Remove common prefixes to focus on item data
        clean_text = text.lower()
        
        # Remove "invoice" and customer name (first word after invoice)
        clean_text = re.sub(r"^invoice\s+[a-zA-Z]+\s*", "", clean_text)
        
        # Strip currency symbols/prefixes so amounts are clean digits
        clean_text = clean_text.replace("₦", "").replace("$", "")
        clean_text = re.sub(r"\busd\b", "", clean_text)
        clean_text = re.sub(r"\bngn\b", "", clean_text)
        
        for word in ["for", "due", "tomorrow", "today", "next week"]:
            clean_text = clean_text.replace(word, " ")
        
        # Remove phone number from text (include +prefix)
        # IMPORTANT: Sort by length descending to avoid partial replacements
        for variant in sorted(phone_variants, key=len, reverse=True):
            clean_text = clean_text.replace("+" + variant.lower(), " ")
            clean_text = clean_text.replace(variant.lower(), " ")
        
        # Also remove phone patterns directly (including + prefix)
        clean_text = re.sub(r"\+?" + self.PHONE_PATTERN.pattern, " ", clean_text)
        
        # Remove email from text
        clean_text = self.EMAIL_PATTERN.sub(" ", clean_text)
        
        # Normalize comma-formatted numbers FIRST
        # Convert "11,000" to "11000" but handle edge cases
        # Pattern: digit,digit (e.g., "11,000" but not "wig, shoe")
        # Also handle typos like "20,00" (2 digits after comma) → "2000"
        clean_text = re.sub(r"(\d),(\d{3})\b", r"\1\2", clean_text)  # 11,000 → 11000
        clean_text = re.sub(r"(\d),(\d{2})\b", r"\1\2", clean_text)  # 20,00 → 2000 (typo)
        clean_text = re.sub(r"(\d),(\d{1})\b", r"\1\2", clean_text)  # 5,0 → 50 (edge case)
        
        # Remove any remaining commas (now safe since amounts are normalized)
        clean_text = clean_text.replace(",", " ")
        
        # Normalize whitespace
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        
        # Strategy: Use regex to find all <amount> <description> pairs
        # or <quantity> <description> at <amount> patterns
        # Pattern: number (3+ digits) followed by non-numeric words until next number
        # This handles both comma-separated and space-separated items
        
        # Also support quantity prefix: "3 wigs" (small number before a word)
        # Vs amount: "5000 wig" (large number before a word)
        
        # Find all amounts and their positions
        amount_pattern = re.compile(r"\b(\d{3,})\b")
        matches = list(amount_pattern.finditer(clean_text))
        
        if not matches:
            return lines
        
        for i, match in enumerate(matches):
            amount_str = match.group(1)
            
            # Skip if it looks like a phone number
            if amount_str in phone_variants:
                continue
            
            amount_start = match.end()
            
            # Description ends at next amount or end of string
            if i + 1 < len(matches):
                desc_end = matches[i + 1].start()
            else:
                desc_end = len(clean_text)
            
            # Extract description between this amount and the next
            description = clean_text[amount_start:desc_end].strip()
            
            # Clean up description - remove leading/trailing punctuation
            description = re.sub(r"^[\s,]+|[\s,]+$", "", description)
            
            if description and not description.isdigit():
                lines.append({
                    "description": description.capitalize(),
                    "quantity": 1,
                    "unit_price": Decimal(amount_str),
                })
        
        # Fallback: if no lines found with amount-first, try item-first pattern
        # e.g., "wig 1000, shoe 2000"
        if not lines:
            tokens = clean_text.split()
            i = 0
            while i < len(tokens) - 1:
                # Check if current token is non-numeric and next is amount
                current = tokens[i]
                next_token = tokens[i + 1]
                
                if not current[0].isdigit() and next_token.isdigit() and len(next_token) >= 3:
                    if next_token not in phone_variants:
                        lines.append({
                            "description": current.capitalize(),
                            "quantity": 1,
                            "unit_price": Decimal(next_token),
                        })
                        i += 2
                        continue
                i += 1
        
        return lines
    
    def _extract_description(self, text: str) -> str:
        """Extract item description from text (for single-item invoices)."""
        # Look for "for <description>" pattern
        for_match = re.search(r"\bfor\s+([a-zA-Z][a-zA-Z\s]+?)(?:\s+due|\s*$)", text, re.IGNORECASE)
        if for_match:
            return for_match.group(1).strip().capitalize()
        
        # Default description
        return "Item"
