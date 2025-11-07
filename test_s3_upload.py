#!/usr/bin/env python3
"""
Test S3 Upload Functionality
Tests if the backend can successfully upload files to suoops-s3-bucket
"""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings
from app.storage.s3_client import S3Client
import os
import pytest


@pytest.mark.integration
def test_s3_upload():
    """Test S3 upload with a sample file (integration gated)."""
    if not os.getenv("INTEGRATION"):
        pytest.skip("Skipping S3 upload test (set INTEGRATION=1 to run)")
    print("🧪 Testing S3 Upload to suoops-s3-bucket...")
    print("=" * 60)
    
    settings = get_settings()
    
    # Display configuration
    print(f"\n📋 S3 Configuration:")
    print(f"  Bucket: {settings.S3_BUCKET}")
    print(f"  Region: {settings.S3_REGION}")
    print(f"  Access Key: {settings.S3_ACCESS_KEY[:10]}...")
    print(f"  Endpoint: {settings.S3_ENDPOINT or 'AWS S3 (default)'}")
    
    # Initialize S3 client
    s3_client = S3Client()
    
    print("\n✅ S3 Client initialized successfully")
    
    # Create a test file
    test_content = b"Hello from SuoOps! This is a test upload."
    test_key = "test/test-upload.txt"
    
    print(f"\n📤 Uploading test file: {test_key}")
    
    try:
        url = s3_client.upload_bytes(data=test_content, key=test_key, content_type="text/plain")
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"S3 upload failed: {e}")
    print(f"✅ Upload successful! URL: {url}")
    assert url and isinstance(url, str)


if __name__ == "__main__":
    success = test_s3_upload()
    sys.exit(0 if success else 1)
