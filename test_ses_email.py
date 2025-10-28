#!/usr/bin/env python3
"""
Test Amazon SES Email Sending
Tests SMTP connection and email delivery
"""
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings


def test_ses_email():
    """Test SES email sending"""
    print("📧 Testing Amazon SES Email Configuration...")
    print("=" * 60)
    
    settings = get_settings()
    
    # Get email configuration (you'll need to add these to config.py)
    smtp_host = getattr(settings, 'SES_SMTP_HOST', None)
    smtp_port = getattr(settings, 'SES_SMTP_PORT', 587)
    smtp_user = getattr(settings, 'SES_SMTP_USER', None)
    smtp_password = getattr(settings, 'SES_SMTP_PASSWORD', None)
    from_email = getattr(settings, 'FROM_EMAIL', None)
    
    # Display configuration
    print(f"\n📋 Email Configuration:")
    print(f"  SMTP Host: {smtp_host or 'NOT SET'}")
    print(f"  SMTP Port: {smtp_port}")
    print(f"  SMTP User: {smtp_user[:20] + '...' if smtp_user else 'NOT SET'}")
    print(f"  From Email: {from_email or 'NOT SET'}")
    
    if not all([smtp_host, smtp_user, smtp_password, from_email]):
        print("\n❌ Email configuration incomplete!")
        print("\nMissing environment variables:")
        if not smtp_host:
            print("  • SES_SMTP_HOST")
        if not smtp_user:
            print("  • SES_SMTP_USER")
        if not smtp_password:
            print("  • SES_SMTP_PASSWORD")
        if not from_email:
            print("  • FROM_EMAIL")
        
        print("\nSet them with:")
        print("  heroku config:set SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com -a suoops-backend")
        print("  heroku config:set SES_SMTP_USER=<your-smtp-username> -a suoops-backend")
        print("  heroku config:set SES_SMTP_PASSWORD=<your-smtp-password> -a suoops-backend")
        print("  heroku config:set FROM_EMAIL=noreply@suoops.com -a suoops-backend")
        return False
    
    # Get recipient email
    print("\n" + "=" * 60)
    to_email = input("Enter recipient email address to test: ").strip()
    
    if not to_email or '@' not in to_email:
        print("❌ Invalid email address!")
        return False
    
    # Create test email
    print(f"\n📤 Sending test email to {to_email}...")
    
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = "Test Email from SuoOps - Amazon SES Configuration"
    
    body = f"""
Hello!

This is a test email from SuoOps to verify Amazon SES configuration.

Configuration Details:
- SMTP Host: {smtp_host}
- SMTP Port: {smtp_port}
- From Email: {from_email}
- Timestamp: {__import__('datetime').datetime.now().isoformat()}

If you received this email, your Amazon SES setup is working correctly! 🎉

Next steps:
1. Request production access in SES console (if in sandbox mode)
2. Configure email templates for invoices and notifications
3. Set up bounce and complaint handling

Best regards,
SuoOps Team

---
This is an automated test email. Please do not reply.
"""
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        # Connect to SMTP server
        print(f"🔌 Connecting to {smtp_host}:{smtp_port}...")
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.set_debuglevel(0)  # Set to 1 for verbose output
        
        # Start TLS
        print("🔒 Starting TLS encryption...")
        server.starttls()
        
        # Login
        print("🔑 Authenticating...")
        server.login(smtp_user, smtp_password)
        
        # Send email
        print("📧 Sending email...")
        server.send_message(msg)
        
        # Close connection
        server.quit()
        
        print("\n" + "=" * 60)
        print("✅ EMAIL SENT SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📬 Check your inbox at: {to_email}")
        print("   (Don't forget to check spam folder)")
        
        print("\n🎉 Amazon SES is configured correctly!")
        print("\n📋 Next Steps:")
        print("  1. Check SES console for delivery status")
        print("  2. Request production access (if in sandbox)")
        print("  3. Integrate email notifications in your app")
        
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"\n❌ SMTP Authentication Failed!")
        print(f"Error: {e}")
        print("\n🔧 Troubleshooting:")
        print("  1. Verify SMTP username and password")
        print("  2. Check you're using eu-north-1 credentials")
        print("  3. Regenerate SMTP credentials in SES console")
        return False
        
    except smtplib.SMTPException as e:
        print(f"\n❌ SMTP Error!")
        print(f"Error: {e}")
        print("\n🔧 Troubleshooting:")
        print("  1. Check SMTP host and port")
        print("  2. Verify network connectivity")
        print("  3. Check firewall settings")
        return False
        
    except Exception as e:
        print(f"\n❌ Unexpected Error!")
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Amazon SES Email Test Script")
    print("  SuoOps - Invoice Management System")
    print("=" * 60 + "\n")
    
    success = test_ses_email()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ Test completed successfully!")
    else:
        print("❌ Test failed. See errors above.")
    print("=" * 60 + "\n")
    
    sys.exit(0 if success else 1)
