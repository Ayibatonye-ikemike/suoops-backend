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
    # Test with OTP email (simpler, doesn't need invoice model)
    result = await ns.send_otp_email(
        to_email="info@suoops.com",
        otp_code="123456"
    )
    
    if result:
        print('✅ Email sent successfully!')
        print('📧 Check info@suoops.com inbox for OTP email')
    else:
        print('❌ Email failed to send')

if __name__ == "__main__":
    asyncio.run(test_email())
