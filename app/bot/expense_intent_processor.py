"""
Expense intent processor for WhatsApp messages.

Handles expense-related messages: text, voice, and photo receipts.
"""
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.bot.whatsapp_client import WhatsAppClient
from app.models.expense import Expense
from app.services.expense_nlp_service import ExpenseNLPService
from app.services.expense_ocr_service import ExpenseOCRService

logger = logging.getLogger(__name__)


class ExpenseIntentProcessor:
    """Process expense-related WhatsApp messages"""
    
    def __init__(self, db: Session, client: WhatsAppClient):
        self.db = db
        self.client = client
        self.nlp_service = ExpenseNLPService()
        self.ocr_service = ExpenseOCRService(db)
    
    async def handle(
        self,
        sender: str,
        parse: dict[str, Any],
        message: dict[str, Any],
    ) -> bool:
        """
        Handle expense intent from parsed message.
        
        Args:
            sender: WhatsApp phone number
            parse: Parsed message from NLP service
            message: Raw WhatsApp message
        
        Returns:
            True if the message was handled as an expense, False otherwise.
        """
        # Check if this is an expense-related message
        if not self._is_expense_message(parse, message):
            return False
        
        # Get user from phone number (handle all Nigerian phone format variants)
        from app.models.models import User
        clean_digits = "".join(ch for ch in sender if ch.isdigit())
        phone_candidates: set[str] = {sender}
        if sender.startswith("+"):
            phone_candidates.add(sender[1:])
        if clean_digits:
            phone_candidates.add(clean_digits)
            if clean_digits.startswith("234"):
                phone_candidates.add(f"+{clean_digits}")
                phone_candidates.add("0" + clean_digits[3:])
            elif clean_digits.startswith("0"):
                phone_candidates.add("234" + clean_digits[1:])
                phone_candidates.add("+234" + clean_digits[1:])
        user = (
            self.db.query(User)
            .filter(User.phone.in_(list(phone_candidates)))
            .first()
        )
        
        if not user:
            self.client.send_text(
                sender,
                "❌ Your number isn't linked to an account yet.\n\n"
                "Register free at suoops.com to start tracking invoices & expenses!"
            )
            return True  # Handled (sent error message)
        
        try:
            # Process based on message type
            msg_type = message.get("type", "text")
            
            if msg_type == "image":
                await self._handle_photo_receipt(user.id, sender, message)
            else:
                await self._handle_text_expense(user.id, sender, parse, message)
        
            return True  # Handled (created expense or sent confirmation)

        except ValueError as e:
            # Handle validation errors (e.g., couldn't extract amount)
            error_msg = str(e)
            logger.warning(f"Validation error processing expense for {sender}: {error_msg}")
            
            if "amount" in error_msg.lower():
                self.client.send_text(
                    sender,
                    "❌ I couldn't find an amount in your message.\n\n"
                    "*How to record an expense:*\n"
                    "• `Expense: ₦5,000 for transport`\n"
                    "• `Spent 3000 naira on data`\n"
                    "• `₦2,500 fuel`\n\n"
                    "Please include an amount (e.g., ₦5,000 or 5000 naira)."
                )
            else:
                self.client.send_text(
                    sender,
                    "❌ I couldn't process that expense.\n\n"
                    "*How to record an expense:*\n"
                    "• `Expense: ₦5,000 for transport`\n"
                    "• `Spent 3000 naira on data`\n\n"
                    "Please check the format and try again."
                )
            return True  # Handled (sent error message)
        
        except Exception as e:
            # Handle unexpected errors gracefully
            error_str = str(e).lower()
            logger.error(f"Error processing expense for {sender}: {e}", exc_info=True)
            
            # Database constraint errors
            if "not-null" in error_str or "notnull" in error_str:
                self.client.send_text(
                    sender,
                    "❌ Something was missing from your expense.\n\n"
                    "*Please try again with this format:*\n"
                    "`Expense: ₦5,000 for [description]`\n\n"
                    "Example: `Expense: ₦3,500 for transport to Lekki`"
                )
            # Connection/timeout errors
            elif "connection" in error_str or "timeout" in error_str:
                self.client.send_text(
                    sender,
                    "❌ Network issue. Please try again in a moment."
                )
            # Generic fallback - user-friendly message
            else:
                self.client.send_text(
                    sender,
                    "❌ Sorry, I couldn't process that expense.\n\n"
                    "*Tips:*\n"
                    "• Make sure to include an amount (e.g., ₦5,000)\n"
                    "• Add a description (e.g., for transport)\n\n"
                    "*Example:*\n"
                    "`Expense: ₦2,500 for data subscription`\n\n"
                    "Or send a photo of your receipt 📸"
                )
            return True  # Handled (sent error message)
    
    def _is_expense_message(
        self,
        parse: dict[str, Any],
        message: dict[str, Any],
    ) -> bool:
        """
        Check if message is about an expense.
        
        Triggers:
        - Contains "expense" keyword
        - Contains amount + expense keywords
        - Image message (assume receipt)
        
        Exclusions:
        - If intent is create_invoice, skip expense processing
        """
        # Skip if this is an invoice request
        intent = getattr(parse, 'intent', None) if hasattr(parse, 'intent') else parse.get('intent')
        if intent == 'create_invoice':
            return False
        
        msg_type = message.get("type", "text")
        
        # Images are assumed to be receipts
        if msg_type == "image":
            return True
        
        # Check text content
        text = message.get("text", "").lower()
        
        # Skip if message contains "invoice" - likely an invoice request
        if "invoice" in text:
            return False
        
        expense_keywords = [
            "expense", "spent", "paid for", "bought",
            "purchase", "cost", "receipt"
        ]
        
        # Check for expense keywords
        for keyword in expense_keywords:
            if keyword in text:
                return True
        
        # Check if contains amount (₦ or naira)
        if "₦" in text or "naira" in text or "ngn" in text:
            # Check for expense-related words nearby
            expense_context = [
                "for", "on", "rent", "data", "transport", "fuel",
                "supplies", "equipment", "repair"
            ]
            for word in expense_context:
                if word in text:
                    return True
        
        return False
    
    async def _handle_text_expense(
        self,
        user_id: int,
        sender: str,
        parse: dict[str, Any],
        message: dict[str, Any],
    ) -> None:
        """
        Handle text-based expense message.
        
        Examples:
        - "Expense: ₦2,000 for internet data on Nov 10"
        - "₦5,000 market rent"
        - "Spent 3000 naira on transport"
        """
        text = message.get("text", "")
        
        # Extract expense details using NLP
        expense_data = self.nlp_service.extract_expense(text)
        
        # Ensure date is never None (database constraint)
        from datetime import date as date_type
        expense_date = expense_data["date"] or date_type.today()
        
        # Create expense record
        expense = Expense(
            user_id=user_id,
            amount=expense_data["amount"],
            date=expense_date,
            category=expense_data["category"],
            description=expense_data["description"],
            merchant=expense_data["merchant"],
            input_method="text",
            channel="whatsapp",
            verified=False,  # User should review
        )
        
        self.db.add(expense)
        self.db.commit()
        self.db.refresh(expense)
        
        # Send confirmation
        await self._send_confirmation(sender, expense)
    
    async def _handle_photo_receipt(
        self,
        user_id: int,
        sender: str,
        message: dict[str, Any],
    ) -> None:
        """
        Handle receipt photo message.
        
        Steps:
        1. Download image from WhatsApp
        2. OCR extraction
        3. Create expense record
        4. Send confirmation
        """
        media_id = message.get("image_id")
        if not media_id:
            self.client.send_text(sender, "❌ Could not get image from message")
            return
        
        # Download image from WhatsApp
        try:
            image_bytes = await self.client.download_media(media_id)
        except Exception as e:
            logger.error(f"Failed to download image {media_id}: {e}")
            self.client.send_text(sender, "❌ Could not download image. Please try again.")
            return
        
        # Send processing message
        self.client.send_text(sender, "📸 Processing receipt... please wait.")
        
        # Process receipt with OCR
        try:
            expense = await self.ocr_service.process_receipt(
                user_id=user_id,
                image_bytes=image_bytes,
                channel="whatsapp",
            )
            
            # Send confirmation
            await self._send_confirmation(sender, expense, is_photo=True)
        
        except Exception as e:
            logger.error(f"OCR processing failed: {e}", exc_info=True)
            self.client.send_text(
                sender,
                "❌ Could not read this receipt.\n\n"
                "📸 *Tips for better results:*\n"
                "• Use a clear, well-lit photo\n"
                "• Make sure the amount is visible\n\n"
                "Or type the expense manually:\n"
                "• `Expense: ₦5,000 for transport`"
            )
    
    async def _send_confirmation(
        self,
        sender: str,
        expense: Expense,
        is_photo: bool = False,
    ) -> None:
        """Send expense confirmation to user"""
        
        # Format date
        date_str = expense.date.strftime("%b %d, %Y") if expense.date else "Today"
        
        # Format category
        category_display = expense.category.replace("_", " ").title()
        
        # Build message
        icon = "📸" if is_photo else "✅"
        message = (
            f"{icon} Expense added!\n\n"
            f"💰 Amount: ₦{expense.amount:,.0f}\n"
            f"📅 Date: {date_str}\n"
            f"📂 Category: {category_display}\n"
        )
        
        if expense.description:
            message += f"📝 Description: {expense.description}\n"
        
        if expense.merchant:
            message += f"🏪 Merchant: {expense.merchant}\n"
        
        if is_photo and not expense.verified:
            message += "\n⚠️ Please review OCR results for accuracy"
        
        self.client.send_text(sender, message)
