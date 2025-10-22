# AWS S3 Configuration Guide

## Bucket Information
- **Bucket Name:** `suopay-s3-bucket`
- **Region:** `eu-north-1` (Europe - Stockholm)
- **Purpose:** Store invoice PDFs and business logos

## Configuration Status
✅ AWS S3 credentials configured in Heroku (v44)
✅ Local `.env` file updated
✅ S3 client updated to support AWS regions

## Required CORS Configuration

To allow the frontend to access uploaded files (PDFs and logos), you need to configure CORS on your S3 bucket:

### Steps to Configure CORS in AWS Console:

1. **Go to AWS S3 Console**
   - Navigate to: https://s3.console.aws.amazon.com/s3/
   - Select your bucket: `suopay-s3-bucket`

2. **Open Permissions Tab**
   - Click on the "Permissions" tab
   - Scroll down to "Cross-origin resource sharing (CORS)"
   - Click "Edit"

3. **Add CORS Policy**
   Paste this JSON configuration:

```json
[
    {
        "AllowedHeaders": [
            "*"
        ],
        "AllowedMethods": [
            "GET",
            "PUT",
            "POST",
            "DELETE",
            "HEAD"
        ],
        "AllowedOrigins": [
            "https://suopay.io",
            "https://www.suopay.io",
            "https://api.suopay.io",
            "http://localhost:3000"
        ],
        "ExposeHeaders": [
            "ETag",
            "x-amz-request-id"
        ],
        "MaxAgeSeconds": 3000
    }
]
```

4. **Save Changes**

## Bucket Policy (Public Read for PDFs)

If you want invoice PDFs to be publicly accessible (recommended for customer access), add this bucket policy:

### Steps to Add Bucket Policy:

1. In S3 Console → Select bucket → Permissions tab
2. Scroll to "Bucket policy" → Click "Edit"
3. Add this policy (replace `suopay-s3-bucket` if different):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadForInvoicePDFs",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::suopay-s3-bucket/*"
        }
    ]
}
```

⚠️ **Note:** This makes all files in the bucket publicly readable. If you prefer private access only, skip this and use presigned URLs (already implemented in the code).

## IAM User Permissions

Your IAM user needs these permissions:
- `s3:PutObject` - Upload files
- `s3:GetObject` - Download files
- `s3:DeleteObject` - Delete files
- `s3:ListBucket` - List bucket contents

### Recommended IAM Policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                "s3:PutObjectAcl"
            ],
            "Resource": [
                "arn:aws:s3:::suopay-s3-bucket",
                "arn:aws:s3:::suopay-s3-bucket/*"
            ]
        }
    ]
}
```

## Environment Variables

### Production (Heroku)
Already configured via Heroku CLI:
```bash
S3_ACCESS_KEY=AKIAZVFYA3GDUWLKSF6C
S3_SECRET_KEY=VnnO/oU5APSXWYw8GPpKFNQeyQXS+0xjptkrU6b
S3_BUCKET=suopay-s3-bucket
S3_REGION=eu-north-1
```

### Local Development (.env)
```bash
S3_ACCESS_KEY=AKIAZVFYA3GDUWLKSF6C
S3_SECRET_KEY=VnnO/oU5APSXWYw8GPpKFNQeyQXS+0xjptkrU6b
S3_BUCKET=suopay-s3-bucket
S3_REGION=eu-north-1
# Leave S3_ENDPOINT empty for AWS S3
```

## Testing S3 Upload

After configuring CORS and deploying, test with:

### 1. Test Logo Upload
```bash
# Login and get access token
curl -X POST https://api.suopay.io/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"+2348012345678","password":"yourpassword"}'

# Upload logo (replace TOKEN with your access token)
curl -X POST https://api.suopay.io/users/me/logo \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@/path/to/logo.png"
```

### 2. Test Invoice PDF Generation
```bash
# Create invoice (will upload PDF to S3)
curl -X POST https://api.suopay.io/invoices \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Test Customer",
    "customer_email": "test@example.com",
    "amount": 10000,
    "lines": [{"description": "Test Item", "quantity": 1, "unit_price": 10000}]
  }'
```

## File Structure in S3

```
suopay-s3-bucket/
├── invoices/
│   └── INV-XXXXXX.pdf
└── logos/
    └── user-{user_id}-{timestamp}.png
```

## Cost Estimation

**Stockholm Region (eu-north-1) Pricing:**
- **Storage:** ~$0.023 per GB/month
- **PUT Requests:** $0.0050 per 1,000 requests
- **GET Requests:** $0.0004 per 1,000 requests

**Estimated Monthly Cost (for 1,000 invoices):**
- Storage (1,000 PDFs @ 100KB each): 100MB = **$0.002**
- PUT requests (1,000 uploads): **$0.005**
- GET requests (5,000 downloads): **$0.002**
- **Total:** ~$0.01/month for 1,000 invoices

Very affordable! 🎉

## Troubleshooting

### Issue: "Access Denied" Error
- **Solution:** Check IAM user permissions include `s3:PutObject` and `s3:GetObject`

### Issue: CORS Error in Browser
- **Solution:** Add your frontend domain to CORS AllowedOrigins

### Issue: "NoSuchBucket" Error
- **Solution:** Verify bucket name and region are correct in env vars

### Issue: Presigned URLs Not Working
- **Solution:** Check S3_REGION matches your bucket's actual region (eu-north-1)

## Security Best Practices

✅ **Implemented:**
- Access keys stored in environment variables (not in code)
- Presigned URLs with 1-hour expiration
- HTTPS-only access

📋 **Recommended:**
- Rotate access keys every 90 days
- Enable S3 bucket versioning for backup
- Set up S3 lifecycle policies to archive old invoices
- Enable CloudTrail for audit logging

## Next Steps

1. ✅ Configure CORS policy (see above)
2. ✅ (Optional) Configure bucket policy for public access
3. ✅ Deploy backend with S3 changes
4. ✅ Test logo upload and invoice generation
5. ✅ Monitor S3 usage in AWS Console

---

**Configuration completed on:** October 22, 2025  
**Heroku deployment:** v44
