"""Test email extraction from WhatsApp messages"""
from app.bot.nlp_service import NLPService

def test_email_extraction():
    nlp = NLPService()
    
    test_cases = [
        {
            "text": "Invoice Jane 50000 for logo design email jane@example.com",
            "expected_email": "jane@example.com",
            "description": "Email at end"
        },
        {
            "text": "Invoice john@company.co.uk John Smith 75000 for consulting",
            "expected_email": "john@company.co.uk",
            "description": "Email in middle"
        },
        {
            "text": "Invoice Sarah 30k email sarah.doe@business.ng phone +2348087654321",
            "expected_email": "sarah.doe@business.ng",
            "description": "Email with phone"
        },
        {
            "text": "Invoice Mike 100000 for website development",
            "expected_email": None,
            "description": "No email provided"
        },
        {
            "text": "Invoice Peter info@suoops.com 45000 for marketing",
            "expected_email": "info@suoops.com",
            "description": "Business email"
        }
    ]
    
    print("🧪 Testing Email Extraction from WhatsApp Messages\n")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        text = test["text"]
        expected = test["expected_email"]
        description = test["description"]
        
        result = nlp.parse_text(text)
        extracted_email = result.entities.get("customer_email")
        
        status = "✅ PASS" if extracted_email == expected else "❌ FAIL"
        
        if extracted_email == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"\nTest {i}: {description}")
        print(f"Input: {text}")
        print(f"Expected: {expected}")
        print(f"Got: {extracted_email}")
        print(f"Status: {status}")
        print("-" * 60)
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
    
    return failed == 0

if __name__ == "__main__":
    success = test_email_extraction()
    exit(0 if success else 1)
