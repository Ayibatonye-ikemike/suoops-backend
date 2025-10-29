"""Test email sending with Brevo SMTP"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

def test_email():
    print(f"Testing email with:")
    print(f"  SMTP Host: {settings.SMTP_HOST}")
    print(f"  SMTP Port: {settings.SMTP_PORT}")
    print(f"  SMTP User: {settings.SMTP_USER}")
    print(f"  From Email: {settings.FROM_EMAIL}")
    print(f"  Email Provider: {settings.EMAIL_PROVIDER}")
    print()
    
    try:
        # Create simple test email
        msg = MIMEMultipart()
        msg['From'] = settings.FROM_EMAIL
        # Change this to YOUR email address to test
        test_recipient = input("Enter your email address to test: ").strip()
        msg['To'] = test_recipient
        msg['Subject'] = "✅ Brevo SMTP Test - SuoOps Email Working!"
        
        body = """
Hello!

This is a test email from your SuoOps backend to verify Brevo SMTP is working correctly.

Configuration:
- SMTP Host: smtp-relay.brevo.com
- SMTP Port: 587
- Email Provider: Brevo (Sendinblue)
- Free Tier: 300 emails/day

If you're reading this, email delivery is working perfectly! 🎉

---
Powered by SuoOps via Brevo
"""
        msg.attach(MIMEText(body, 'plain'))
        
        # Send via SMTP
        print("📤 Connecting to Brevo SMTP...")
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            print("🔐 Starting TLS...")
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            print("✅ Logged in successfully!")
            server.send_message(msg)
            print("📧 Email sent successfully!")
        
        print()
        print('✅ SUCCESS! Email sent to info@suoops.com')
        print('📧 Check your inbox for the test email')
        return True
        
    except Exception as e:
        print(f'❌ FAILED: {type(e).__name__}: {e}')
        return False

if __name__ == "__main__":
    test_email()
