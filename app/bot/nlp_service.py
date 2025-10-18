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
    AMOUNT_PATTERN = re.compile(r"(?:₦|ngn)?\s?([0-9]{3,}(?:,[0-9]{3})*|[0-9]+)(?:\.[0-9]{1,2})?")

    def parse_text(self, text: str) -> ParseResult:
        lower = text.lower()
        if "invoice" in lower:
            entities = self._extract_invoice(lower)
            return ParseResult(intent="create_invoice", entities=entities)
        return ParseResult(intent="unknown", entities={}, confidence=0.2)

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
