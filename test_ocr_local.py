#!/usr/bin/env python3
"""Integration-oriented OCR smoke tests (gated by INTEGRATION env)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
import io
from PIL import Image, ImageDraw, ImageFont  # noqa: I001

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.ocr_service import OCRService


@pytest.mark.skipif(not os.getenv("INTEGRATION"), reason="OCR integration requires OpenAI API key")
async def test_ocr_basic():
    """Test OCR service initialization and basic config."""
    print("=" * 60)
    print("Testing OCR Service Configuration")
    print("=" * 60)
    
    try:
        ocr = OCRService()
        print("✅ OCR Service initialized")
        print(f"   Model: {ocr.model}")
        print(f"   API URL: {ocr.api_url}")
        print(f"   API Key: {'*' * 20}{ocr.api_key[-10:] if ocr.api_key else 'NOT SET'}")
        print(f"   Max Image Size: {ocr.max_image_size}")

        if not ocr.api_key:
            print("\n❌ ERROR: OPENAI_API_KEY not set in environment!")
            return False

        print("\n✅ All configurations look good!")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


@pytest.mark.skipif(not os.getenv("INTEGRATION"), reason="OCR integration requires OpenAI API key")
async def test_ocr_with_simple_image():
    """Test OCR with a minimal test image."""
    print("\n" + "=" * 60)
    print("Testing OCR with Simple Test Image")
    print("=" * 60)

    try:
        # Create a simple test receipt image
        img = Image.new("RGB", (800, 600), color="white")
        draw = ImageDraw.Draw(img)

        # Draw simple receipt text
        try:
            font = ImageFont.load_default()
        except Exception:  # noqa: BLE001
            font = None

        text = (
            "INVOICE\n\n"
            "Customer: Test Customer\n"
            "Amount: ₦50,000\n\n"
            "Items:\n"
            "1x Logo Design - ₦50,000\n\n"
            "Total: ₦50,000\n"
        )
        draw.text((50, 50), text, fill="black", font=font)

        # Convert to bytes
        img_bytes_io = io.BytesIO()
        img.save(img_bytes_io, format="JPEG")
        img_bytes = img_bytes_io.getvalue()
        print(f"Created test image: {len(img_bytes)} bytes")

        # Test OCR
        ocr = OCRService()
        print("\n🔄 Calling OpenAI Vision API...")
        print("   (This may take 5-10 seconds)")
        result = await ocr.parse_receipt(img_bytes, context="test invoice")

        print("\n" + "=" * 60)
        print("OCR RESULT:")
        print("=" * 60)

        if result.get("success"):
            print("✅ OCR Successful!")
            print("\n📋 Extracted Data:")
            print(f"   Customer: {result.get('customer_name', 'N/A')}")
            print(f"   Amount: ₦{result.get('amount', 'N/A')}")
            print(f"   Currency: {result.get('currency', 'N/A')}")
            print(f"   Confidence: {result.get('confidence', 'N/A')}")

            items = result.get("items", [])
            if items:
                print(f"\n   Items ({len(items)}):")
                for i, item in enumerate(items, 1):
                    desc = item.get("description", "N/A")
                    qty = item.get("quantity", 1)
                    price = item.get("unit_price", "N/A")
                    print(f"     {i}. {desc} (x{qty}) @ ₦{price}")

            raw_text = result.get("raw_text", "")
            if raw_text:
                print(f"\n   Raw Text Preview: {raw_text[:100]}...")
            return True

        error = result.get("error", "Unknown error")
        print(f"❌ OCR Failed: {error}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ ERROR during OCR test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n🚀 Starting OCR Service Tests\n")
    
    # Test 1: Basic configuration
    config_ok = await test_ocr_basic()
    
    if not config_ok:
        print("\n❌ Configuration test failed. Fix issues before continuing.")
        return 1
    
    # Test 2: Actual OCR with test image
    ocr_ok = await test_ocr_with_simple_image()
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Configuration: {'✅ PASS' if config_ok else '❌ FAIL'}")
    print(f"OCR Processing: {'✅ PASS' if ocr_ok else '❌ FAIL'}")
    
    if config_ok and ocr_ok:
        print("\n🎉 All tests passed! OCR service is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    # Allow running standalone; respect INTEGRATION flag
    if not os.getenv("INTEGRATION"):
        print("INTEGRATION flag not set; skipping OCR tests.")
        sys.exit(0)
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
