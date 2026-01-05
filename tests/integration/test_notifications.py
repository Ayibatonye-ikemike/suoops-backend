"""Test invoice notifications (Email, WhatsApp)"""
import asyncio
import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import models
from app.services.notification.service import NotificationService


async def test_invoice_notifications():
    """Test sending invoice notifications via all channels"""
    
    print("\n" + "="*60)
    print("TESTING INVOICE NOTIFICATIONS")
    print("="*60 + "\n")
    
    db: Session = SessionLocal()
    
    try:
        # Get or create a test user (business owner)
        user = db.query(models.User).filter(models.User.phone == "+2348012345678").first()
        if not user:
            print("❌ Test user not found. Please create a user first.")
            return
        
        print(f"✅ Business User: {user.name}")
        print(f"   Email: {user.email}")
        print(f"   Phone: {user.phone}\n")
        
        # Get or create a test customer
        customer = db.query(models.Customer).filter(
            models.Customer.phone == "+2348087654321"
        ).first()
        
        if not customer:
            customer = models.Customer(
                name="Test Customer",
                phone="+2348087654321",
                email="testcustomer@example.com"
            )
            db.add(customer)
            db.commit()
            print("✅ Created test customer")
        
        print(f"✅ Customer: {customer.name}")
        print(f"   Email: {customer.email}")
        print(f"   Phone: {customer.phone}\n")
        
        # Create a test invoice
        invoice = models.Invoice(
            invoice_id=f"TEST-{int(asyncio.get_event_loop().time())}",
            issuer_id=user.id,
            customer_id=customer.id,
            amount=Decimal("50000.00"),
            status="pending",
            pdf_url="https://example.com/invoice.pdf"
        )
        db.add(invoice)
        db.commit()
        
        print(f"✅ Created invoice: {invoice.invoice_id}")
        print(f"   Amount: ₦{invoice.amount:,.2f}\n")
        
        # Test notifications
        print("-" * 60)
        print("SENDING NOTIFICATIONS TO CUSTOMER...")
        print("-" * 60 + "\n")
        
        notification_service = NotificationService()
        
        results = await notification_service.send_invoice_notification(
            invoice=invoice,
            customer_email=customer.email,
            customer_phone=customer.phone,
            pdf_url=invoice.pdf_url,
        )
        
        print("\n📊 NOTIFICATION RESULTS:")
        print(f"   Email:    {'✅ SUCCESS' if results['email'] else '❌ FAILED'}")
        print(f"   WhatsApp: {'✅ SUCCESS' if results['whatsapp'] else '❌ FAILED'}")
        print()
        
        # Test payment confirmation notification to business
        print("-" * 60)
        print("TESTING PAYMENT CONFIRMATION NOTIFICATION TO BUSINESS...")
        print("-" * 60 + "\n")
        
        # Simulate customer confirming payment
        invoice.status = "awaiting_confirmation"
        db.commit()
        
        message = (
            f"Customer reported a transfer.\n\n"
            f"Invoice: {invoice.invoice_id}\n"
            f"Amount: ₦{invoice.amount:,.2f}\n\n"
            f"Please confirm the funds and mark the invoice as paid."
        )
        
        business_results = {"email": False}
        
        # Send Email to business
        if user.email:
            business_results["email"] = await notification_service.send_email(
                to_email=user.email,
                subject=f"Payment Confirmation - Invoice {invoice.invoice_id}",
                body=message,
            )
        
        print("📊 BUSINESS NOTIFICATION RESULTS:")
        print(f"   Email: {'✅ SUCCESS' if business_results['email'] else '❌ FAILED'}")
        print()
        
        # Cleanup
        db.delete(invoice)
        db.commit()
        print("🧹 Cleaned up test invoice\n")
        
        print("="*60)
        print("TEST COMPLETE")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_invoice_notifications())
