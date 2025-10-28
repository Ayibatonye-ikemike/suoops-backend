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


def test_s3_upload():
    """Test S3 upload with a sample file"""
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
        # Upload the test file (using upload_bytes method)
        url = s3_client.upload_bytes(
            data=test_content,
            key=test_key,
            content_type="text/plain"
        )
        
        print(f"✅ Upload successful!")
        print(f"📍 File URL: {url}")
        
        # Note: S3Client doesn't have file_exists or delete_file methods
        # but the upload itself confirms S3 is working
        print(f"\n✅ S3 connection verified!")
        
        print("\n" + "=" * 60)
        print("🎉 S3 UPLOAD TEST PASSED!")
        print("=" * 60)
        print("\n✅ Your S3 bucket is ready for:")
        print("  • Logo uploads")
        print("  • Invoice PDF storage")
        print("  • Receipt PDF storage")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Upload failed!")
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        
        print("\n" + "=" * 60)
        print("🔧 Troubleshooting Tips:")
        print("=" * 60)
        print("1. Verify bucket exists: suoops-s3-bucket in eu-north-1")
        print("2. Check IAM user has S3 permissions")
        print("3. Verify credentials are correct in Heroku config")
        print("4. Check bucket is not blocked by bucket policies")
        
        return False


if __name__ == "__main__":
    success = test_s3_upload()
    sys.exit(0 if success else 1)
