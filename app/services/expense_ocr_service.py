"""
Expense OCR service for processing receipt photos.

Uses existing OCR infrastructure to extract expense details from receipt images.
Auto-categorizes based on merchant/description and stores receipt evidence.
"""
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TypedDict

from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.services.expense_nlp_service import ExpenseNLPService
from app.services.ocr_service import OCRService
from app.storage.s3_client import S3Client

logger = logging.getLogger(__name__)


class ReceiptData(TypedDict):
    """Parsed receipt information"""
    amount: Decimal
    date: date | None
    category: str
    description: str
    merchant: str | None
    raw_text: str
    confidence: str


class ExpenseOCRService:
    """Process receipt photos to create expense records"""
    
    def __init__(self, db: Session):
        self.db = db
        self.ocr_service = OCRService()
        self.nlp_service = ExpenseNLPService()
        self.s3_client = S3Client()
    
    async def process_receipt(
        self,
        user_id: int,
        image_bytes: bytes,
        channel: str = "whatsapp",
    ) -> Expense:
        """
        Process receipt photo and create expense record.
        
        Steps:
        1. Upload receipt image to S3
        2. OCR extraction
        3. Parse and categorize
        4. Create expense record
        
        Args:
            user_id: User ID
            image_bytes: Receipt image bytes
            channel: Input channel (whatsapp, email)
            
        Returns:
            Created Expense record
        """
        # 1. Upload receipt to S3
        receipt_url = await self._upload_receipt(user_id, image_bytes)
        
        # 2. OCR extraction
        ocr_result = await self.ocr_service.parse_receipt(
            image_bytes,
            context="business expense receipt"
        )
        
        if not ocr_result.get("success"):
            logger.error(f"OCR failed for user {user_id}: {ocr_result.get('error')}")
            raise ValueError(f"Could not read receipt: {ocr_result.get('error', 'Unknown error')}")
        
        # 3. Parse receipt data
        receipt_data = self._parse_ocr_result(ocr_result)
        
        # 4. Create expense record
        expense = Expense(
            user_id=user_id,
            amount=receipt_data["amount"],
            date=receipt_data["date"] or date.today(),
            category=receipt_data["category"],
            description=receipt_data["description"],
            merchant=receipt_data["merchant"],
            input_method="photo",
            channel=channel,
            receipt_url=receipt_url,
            receipt_text=receipt_data["raw_text"],
            verified=receipt_data["confidence"] == "high",  # Auto-verify high-confidence
            notes=f"OCR confidence: {receipt_data['confidence']}",
        )
        
        self.db.add(expense)
        self.db.commit()
        self.db.refresh(expense)
        
        logger.info(
            f"Created expense from receipt for user {user_id}: "
            f"₦{expense.amount}, category={expense.category}"
        )
        
        return expense
    
    async def _upload_receipt(self, user_id: int, image_bytes: bytes) -> str:
        """
        Upload receipt image to S3.
        
        Returns:
            S3 URL of uploaded receipt
        """
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"receipts/user_{user_id}/{timestamp}_receipt.jpg"
        
        # Upload to S3
        receipt_url = await self.s3_client.upload_file(
            file_data=image_bytes,
            object_name=filename,
            content_type="image/jpeg",
        )
        
        return receipt_url
    
    def _parse_ocr_result(self, ocr_result: dict) -> ReceiptData:
        """
        Parse OCR result into structured receipt data.
        
        Args:
            ocr_result: Result from OCR service
            
        Returns:
            Structured receipt data
        """
        # Extract basic info from OCR
        amount_str = ocr_result.get("amount", "0")
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, ValueError):
            amount = Decimal("0")
        
        merchant = ocr_result.get("business_name") or None
        raw_text = ocr_result.get("raw_text", "")
        confidence = ocr_result.get("confidence", "medium")
        
        # Try to parse date from OCR result
        date_str = ocr_result.get("date")
        expense_date = None
        if date_str:
            try:
                expense_date = datetime.fromisoformat(date_str).date()
            except (ValueError, AttributeError):
                pass
        
        # Build description from items or raw text
        items = ocr_result.get("items", [])
        if items:
            # Use item descriptions
            descriptions = [
                item.get("description", "")
                for item in items
                if item.get("description")
            ]
            description = ", ".join(descriptions[:3])  # Top 3 items
        else:
            # Use NLP to extract description from raw text
            description = self.nlp_service._clean_description(raw_text)
        
        # Categorize based on merchant or description
        category_text = f"{merchant or ''} {description} {raw_text}".lower()
        category = self.nlp_service._categorize(category_text)
        
        return ReceiptData(
            amount=amount,
            date=expense_date,
            category=category,
            description=description[:500] if description else "Receipt expense",
            merchant=merchant[:200] if merchant else None,
            raw_text=raw_text,
            confidence=confidence,
        )
    
    async def reprocess_receipt(
        self,
        expense_id: int,
        user_id: int,
    ) -> Expense:
        """
        Reprocess an existing receipt (e.g., after OCR improvements).
        
        Args:
            expense_id: Expense ID
            user_id: User ID (for verification)
            
        Returns:
            Updated Expense record
        """
        expense = self.db.query(Expense).filter(
            Expense.id == expense_id,
            Expense.user_id == user_id,
        ).first()
        
        if not expense:
            raise ValueError("Expense not found")
        
        if not expense.receipt_url:
            raise ValueError("No receipt image to reprocess")
        
        # Download receipt from S3
        # (Would need S3Client.download_file method)
        # For now, just log
        logger.info(f"Would reprocess receipt for expense {expense_id}")
        
        return expense
