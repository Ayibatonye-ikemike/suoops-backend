"""Test email sending with Brevo SMTP"""
import asyncio
from app.core.config import settings
from app.services.notification_service import NotificationService

async def test_email():
    print(f"Testing email with:")
    print(f"  SMTP Host: {settings.SMTP_HOST}")
    print(f"  SMTP Port: {settings.SMTP_PORT}")
    print(f"  SMTP User: {settings.SMTP_USER}")
    print(f"  From Email: {settings.FROM_EMAIL}")
    print(f"  Email Provider: {settings.EMAIL_PROVIDER}")
    print()
    
    ns = NotificationService()
    result = await ns.send_invoice_notification(
        to_email='info@suoops.com',
        customer_name='Test Customer',
        invoice_number='INV-TEST-001',
        amount=50000,
        invoice_link='https://suoops.com'
    )
    
    if result:
        print('✅ Email sent successfully!')
    else:
        print('❌ Email failed to send')

if __name__ == "__main__":
    asyncio.run(test_email())
