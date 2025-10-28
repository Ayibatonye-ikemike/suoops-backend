# AWS S3 and SES Setup for SuoOps

**Date**: October 28, 2025  
**Domain**: suoops.com  
**Region**: eu-north-1 (Europe - Stockholm)

---

## Step 1: Create S3 Bucket

### Via AWS Console:

1. **Go to S3 Console**: https://s3.console.aws.amazon.com/
2. **Click "Create bucket"**
3. **Configure**:
   ```
   Bucket name: suoops-s3-bucket
   Region: Europe (Stockholm) eu-north-1
   ```
4. **Object Ownership**: ACLs disabled (recommended)
5. **Block Public Access**: 
   - ✅ Block all public access (keep private)
   - Or uncheck if you want public PDF access
6. **Bucket Versioning**: Disabled (save costs)
7. **Encryption**: Server-side encryption with Amazon S3 managed keys (SSE-S3)
8. **Click "Create bucket"**

### Via AWS CLI:

```bash
# Create bucket
aws s3 mb s3://suoops-s3-bucket --region eu-north-1

# Configure CORS (if needed for browser uploads)
aws s3api put-bucket-cors --bucket suoops-s3-bucket --cors-configuration file://cors.json
```

**CORS Configuration** (`cors.json`):
```json
{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
      "AllowedOrigins": [
        "https://suoops.com",
        "https://www.suoops.com",
        "https://api.suoops.com"
      ],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
```

---

## Step 2: Create IAM User for S3 Access

### Via AWS Console:

1. **Go to IAM Console**: https://console.aws.amazon.com/iam/
2. **Click "Users"** → **"Create user"**
3. **User name**: `suoops-s3-user`
4. **Access type**: Programmatic access only
5. **Permissions**: Click "Attach policies directly"
6. **Create inline policy** with this JSON:

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
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::suoops-s3-bucket",
        "arn:aws:s3:::suoops-s3-bucket/*"
      ]
    }
  ]
}
```

7. **Create user** and **save the credentials**:
   - Access Key ID
   - Secret Access Key

---

## Step 3: Set Up Amazon SES

### Via AWS Console:

1. **Go to SES Console**: https://console.aws.amazon.com/ses/
2. **Select region**: Europe (Stockholm) eu-north-1
3. **Verify your domain**: suoops.com

#### Verify Domain:

1. **Click "Verified identities"** → **"Create identity"**
2. **Select**: Domain
3. **Domain**: `suoops.com`
4. **Advanced DKIM settings**:
   - ✅ Easy DKIM
   - ✅ Enabled
   - DKIM signing key length: 2048-bit
5. **Click "Create identity"**

#### Add DNS Records to Namecheap:

After creating, AWS will show you DNS records. Add these to Namecheap:

**DKIM Records** (3 CNAME records):
```
Type: CNAME
Host: [random-string-1]._domainkey
Value: [random-string-1].dkim.amazonses.com

Type: CNAME
Host: [random-string-2]._domainkey
Value: [random-string-2].dkim.amazonses.com

Type: CNAME
Host: [random-string-3]._domainkey
Value: [random-string-3].dkim.amazonses.com
```

**DMARC Record** (optional but recommended):
```
Type: TXT
Host: _dmarc
Value: v=DMARC1; p=none; rua=mailto:your-email@suoops.com
```

#### Verify Email Address (for testing):

1. **Click "Create identity"**
2. **Select**: Email address
3. **Email**: your-email@gmail.com (or your actual email)
4. **Check your email** and click the verification link

#### Create SMTP Credentials:

1. **In SES Console**, click **"SMTP settings"** (left sidebar)
2. **Click "Create SMTP credentials"**
3. **IAM User Name**: `suoops-ses-smtp-user`
4. **Click "Create"**
5. **Download** or **copy** the credentials:
   - SMTP Username
   - SMTP Password
   - SMTP Endpoint: `email-smtp.eu-north-1.amazonaws.com`
   - Port: 587 (TLS)

#### Request Production Access:

1. **In SES Console**, click **"Account dashboard"**
2. **If in sandbox mode**, click **"Request production access"**
3. Fill out the form:
   - **Use case**: Transactional emails (invoices, receipts)
   - **Expected send rate**: 100 emails/day
   - **Describe your use case**: "Sending invoice PDFs and payment receipts to customers"
4. **Submit** and wait for approval (usually 24 hours)

---

## Step 4: Configure Heroku

Update all environment variables:

```bash
# S3 Configuration
heroku config:set S3_BUCKET=suoops-s3-bucket -a suoops-backend
heroku config:set S3_REGION=eu-north-1 -a suoops-backend
heroku config:set S3_ACCESS_KEY=YOUR_NEW_ACCESS_KEY -a suoops-backend
heroku config:set S3_SECRET_KEY=YOUR_NEW_SECRET_KEY -a suoops-backend

# SES SMTP Configuration
heroku config:set EMAIL_PROVIDER=ses -a suoops-backend
heroku config:set SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com -a suoops-backend
heroku config:set SES_SMTP_PORT=587 -a suoops-backend
heroku config:set SES_SMTP_USER=YOUR_SMTP_USERNAME -a suoops-backend
heroku config:set SES_SMTP_PASSWORD=YOUR_SMTP_PASSWORD -a suoops-backend
heroku config:set SES_REGION=eu-north-1 -a suoops-backend
heroku config:set FROM_EMAIL=noreply@suoops.com -a suoops-backend
```

---

## Step 5: Test S3 Upload

```bash
# Test file upload
echo "Test file" > test.txt
aws s3 cp test.txt s3://suoops-s3-bucket/test.txt --region eu-north-1

# Verify
aws s3 ls s3://suoops-s3-bucket/ --region eu-north-1

# Clean up
rm test.txt
aws s3 rm s3://suoops-s3-bucket/test.txt
```

---

## Step 6: Test SES Email (After Domain Verification)

```python
import boto3
from botocore.exceptions import ClientError

# Initialize SES client
ses = boto3.client('ses', region_name='eu-north-1')

try:
    response = ses.send_email(
        Source='noreply@suoops.com',
        Destination={'ToAddresses': ['your-email@gmail.com']},
        Message={
            'Subject': {'Data': 'Test Email from SuoOps'},
            'Body': {'Text': {'Data': 'This is a test email from SuoOps!'}}
        }
    )
    print(f"Email sent! Message ID: {response['MessageId']}")
except ClientError as e:
    print(f"Error: {e.response['Error']['Message']}")
```

Or test via Heroku:

```bash
heroku run python -c "
from app.services.notification_service import NotificationService
from app.core.config import settings

service = NotificationService()
# Test email send
print('Email test would go here')
" -a suoops-backend
```

---

## Configuration Summary

### S3 Bucket:
- **Name**: `suoops-s3-bucket`
- **Region**: `eu-north-1`
- **Purpose**: Store invoice PDFs, logos, receipts

### SES:
- **Domain**: `suoops.com` (verified with DKIM)
- **Region**: `eu-north-1`
- **SMTP Endpoint**: `email-smtp.eu-north-1.amazonaws.com`
- **Port**: `587` (STARTTLS)
- **From Email**: `noreply@suoops.com`

### IAM Users:
- **S3 User**: `suoops-s3-user` (S3 access only)
- **SES User**: `suoops-ses-smtp-user` (SMTP credentials)

---

## Cost Estimate

### S3:
- Storage: $0.023/GB/month (Stockholm region)
- Requests: $0.005 per 1,000 PUT/COPY requests
- **Estimated**: ~$0.50/month for 1,000 invoices

### SES:
- First 62,000 emails/month: **FREE** (when sending from EC2/Lambda/Heroku)
- After that: $0.10 per 1,000 emails
- **Estimated**: $0.00/month for typical usage

**Total**: ~$0.50/month

---

## Troubleshooting

### S3 Upload Fails:
```bash
# Check bucket exists
aws s3 ls s3://suoops-s3-bucket --region eu-north-1

# Check IAM permissions
aws iam get-user-policy --user-name suoops-s3-user --policy-name S3Access
```

### SES Email Fails:
```bash
# Check domain verification status
aws ses get-identity-verification-attributes --identities suoops.com --region eu-north-1

# Check if in sandbox mode
aws ses get-account-sending-enabled --region eu-north-1
```

### DNS Not Propagating:
```bash
# Check DKIM records
dig _amazonses.suoops.com TXT

# Check domain verification TXT record
dig suoops.com TXT
```

---

## Next Steps

1. ✅ Create S3 bucket: `suoops-s3-bucket`
2. ✅ Create IAM user for S3
3. ✅ Update Heroku S3 config
4. ✅ Create SES identity for `suoops.com`
5. ✅ Add DNS records to Namecheap
6. ⏳ Wait for domain verification (5-10 minutes)
7. ✅ Create SES SMTP credentials
8. ✅ Update Heroku SES config
9. ✅ Request production access (if needed)
10. ✅ Test email sending

---

## Quick Start Commands

```bash
# 1. Create S3 bucket
aws s3 mb s3://suoops-s3-bucket --region eu-north-1

# 2. Create SES SMTP user (via Console - easier)

# 3. Update Heroku
heroku config:set S3_BUCKET=suoops-s3-bucket \
  S3_REGION=eu-north-1 \
  S3_ACCESS_KEY=AKIA... \
  S3_SECRET_KEY=... \
  SES_SMTP_HOST=email-smtp.eu-north-1.amazonaws.com \
  SES_SMTP_PORT=587 \
  SES_SMTP_USER=... \
  SES_SMTP_PASSWORD=... \
  FROM_EMAIL=noreply@suoops.com \
  -a suoops-backend

# 4. Test
heroku logs --tail -a suoops-backend
```

---

**📞 Need Help?**
- AWS S3 Docs: https://docs.aws.amazon.com/s3/
- AWS SES Docs: https://docs.aws.amazon.com/ses/
- Heroku Config: https://devcenter.heroku.com/articles/config-vars
