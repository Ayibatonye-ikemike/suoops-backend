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
    ) -> None:
        """
        Handle expense intent from parsed message.
        
        Args:
            sender: WhatsApp phone number
            parse: Parsed message from NLP service
            message: Raw WhatsApp message
        """
        # Check if this is an expense-related message
        if not self._is_expense_message(parse, message):
            return
        
        # Get user from phone number
        from app.models.models import User
        user = self.db.query(User).filter(User.phone == sender).first()
        
        if not user:
            self.client.send_text(
                sender,
                "❌ Please register first by creating an invoice."
            )
            return
        
        try:
            # Process based on message type
            msg_type = message.get("type", "text")
            
            if msg_type == "image":
                await self._handle_photo_receipt(user.id, sender, message)
            else:
                await self._handle_text_expense(user.id, sender, parse, message)
        
        except Exception as e:
            logger.error(f"Error processing expense for {sender}: {e}", exc_info=True)
            self.client.send_text(
                sender,
                f"❌ Sorry, I couldn't process that expense: {str(e)}"
            )
    
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
                f"❌ Could not read receipt: {str(e)}\n\n"
                "Try sending a clearer photo or type the expense manually."
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
