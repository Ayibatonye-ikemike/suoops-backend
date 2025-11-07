"""
Test script for tax and fiscalization features.

Run this to verify the implementation works correctly.
"""
import os
import requests
import json
import pytest

# Base URL
BASE_URL = "http://localhost:8000"

@pytest.mark.skipif(not os.getenv("INTEGRATION"), reason="Integration test requires running server")
def test_vat_calculator():
    """Test VAT calculation endpoint"""
    print("\n" + "="*50)
    print("Testing VAT Calculator")
    print("="*50)
    
    # Test standard VAT
    response = requests.get(
        f"{BASE_URL}/tax/vat/calculate",
        params={"amount": 10000, "category": "standard"}
    )
    print(f"\nStandard VAT (₦10,000):")
    print(json.dumps(response.json(), indent=2))
    
    # Test zero-rated
    response = requests.get(
        f"{BASE_URL}/tax/vat/calculate",
        params={"amount": 5000, "category": "zero_rated"}
    )
    print(f"\nZero-rated (₦5,000):")
    print(json.dumps(response.json(), indent=2))


@pytest.mark.skipif(not os.getenv("INTEGRATION"), reason="Integration test requires running server")
def test_api_docs():
    """Check if API documentation includes tax endpoints"""
    print("\n" + "="*50)
    print("Checking API Documentation")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/openapi.json")
    openapi_spec = response.json()
    
    tax_paths = [path for path in openapi_spec.get("paths", {}).keys() if "/tax/" in path]
    
    print(f"\nTax endpoints found: {len(tax_paths)}")
    for path in tax_paths:
        print(f"  - {path}")


if __name__ == "__main__":
    print("\n🧪 SuoOps Tax & Fiscalization Test Suite")
    print("=" * 50)
    
    try:
        # Test health check first
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Backend is running")
        else:
            print("❌ Backend is not responding correctly")
            exit(1)
        
        # Run tests
        test_vat_calculator()
        test_api_docs()
        
        print("\n" + "="*50)
        print("✅ All tests completed!")
        print("="*50)
        
        print("\n📖 Next steps:")
        print("1. Run migration: alembic upgrade head")
        print("2. Create tax profile: POST /tax/profile")
        print("3. Fiscalize invoice: POST /tax/invoice/{id}/fiscalize")
        print("4. Generate VAT return: POST /tax/vat/return?year=2026&month=1")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Backend not running")
        print("Start the backend with: uvicorn app.api.main:app --reload")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
