"""Test email-based signup (temporary pre-launch feature)."""

import requests

API_URL = "https://suoops-backend-e4a267e41e92.herokuapp.com"

# Test email signup
print("🧪 Testing Email Signup...")
print("=" * 50)

# Step 1: Request OTP
print("\n1️⃣ Requesting OTP for test@example.com...")
response = requests.post(
    f"{API_URL}/signup/request",
    json={
        "email": "test@example.com",
        "name": "Test User",
        "business_name": "Test Business"
    }
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 200:
    print("\n✅ OTP request sent successfully!")
    print("📧 Check your email for the OTP code")
    print("\nNext steps:")
    print("1. Get OTP from email")
    print("2. Verify with: POST /signup/verify")
    print('   Body: {"email": "test@example.com", "otp": "123456"}')
else:
    print("\n❌ Failed to send OTP")
    print(f"Error: {response.json()}")

print("\n" + "=" * 50)
print("🎯 Email OTP is now live on production (v88)!")
print("📧 Users can signup with email while WhatsApp is in sandbox")
