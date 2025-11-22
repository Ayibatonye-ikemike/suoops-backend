# SuoOps Environment Management Guide

## Overview
SuoOps uses environment-specific configuration to separate development, staging, and production environments.

## Environment Files

### Development (Local)
- **File**: `.env` (git-ignored)
- **Template**: `.env.development.example`
- **Setup**: 
  ```bash
  cp .env.development.example .env
  # Edit .env with your local values
  ```

### Production (Heroku)
- **File**: None (use Heroku Config Vars)
- **Reference**: `.env.production.example`
- **Setup**:
  ```bash
  heroku config:set KEY=value --app suoops-backend
  ```

## Security Best Practices

### ✅ DO:
1. **Keep secrets in Heroku Config Vars** (not files)
2. **Use test API keys in development** (Paystack test keys)
3. **Rotate secrets quarterly** (JWT_SECRET, API keys)
4. **Use strong JWT secrets** (min 32 characters, random)
5. **Keep .env in .gitignore** (already configured)
6. **Use environment-specific values** (dev DB ≠ prod DB)

### ❌ DON'T:
1. **Commit .env files** (will expose secrets)
2. **Use production keys locally** (risk of accidental charges)
3. **Share secrets via Slack/email** (use 1Password or similar)
4. **Hardcode secrets in code** (always use config)
5. **Use same DB for dev and prod** (data corruption risk)

## Setting Up Environments

### Local Development

1. **Install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.development.example .env
   # Edit .env with your local values:
   # - Use localhost for DATABASE_URL and REDIS_URL
   # - Use Paystack TEST keys (sk_test_xxx)
   # - Use development AWS bucket
   ```

3. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

4. **Start server:**
   ```bash
   uvicorn app.api.main:app --reload
   ```

### Staging Environment (Optional)

For a staging environment on Heroku:

```bash
# Create staging app
heroku create suoops-staging --region us

# Add Postgres and Redis
heroku addons:create heroku-postgresql:mini --app suoops-staging
heroku addons:create heroku-redis:mini --app suoops-staging

# Set environment variables
heroku config:set ENVIRONMENT=staging --app suoops-staging
heroku config:set FRONTEND_URL=https://staging.suoops.com --app suoops-staging
heroku config:set JWT_SECRET=$(openssl rand -hex 32) --app suoops-staging
# ... set other vars from .env.production.example

# Deploy
git push staging main
```

### Production Environment

```bash
# Set all production secrets (from 1Password or secure vault)
heroku config:set JWT_SECRET=$(openssl rand -hex 32) --app suoops-backend
heroku config:set PAYSTACK_SECRET=sk_live_xxxxx --app suoops-backend
heroku config:set BREVO_API_KEY=xkeysib-xxxxx --app suoops-backend
heroku config:set AWS_ACCESS_KEY_ID=xxxxx --app suoops-backend
heroku config:set AWS_SECRET_ACCESS_KEY=xxxxx --app suoops-backend
heroku config:set TWILIO_ACCOUNT_SID=ACxxxxx --app suoops-backend
heroku config:set TWILIO_AUTH_TOKEN=xxxxx --app suoops-backend
heroku config:set FRONTEND_URL=https://suoops.com --app suoops-backend
heroku config:set ENVIRONMENT=production --app suoops-backend
heroku config:set SENTRY_DSN=https://xxxxx@sentry.io/xxxxx --app suoops-backend

# Verify all variables are set
heroku config --app suoops-backend
```

## Accessing Secrets

### In Code
```python
from app.core.config import settings

# Correct way to access secrets
database_url = settings.DATABASE_URL
paystack_key = settings.PAYSTACK_SECRET

# Never hardcode:
# paystack_key = "sk_live_xxxxx"  # ❌ WRONG
```

### In Shell
```bash
# Development
source .env
echo $PAYSTACK_SECRET

# Production
heroku config:get PAYSTACK_SECRET --app suoops-backend
```

## Secret Rotation Schedule

| Secret | Rotation Frequency | How to Rotate |
|--------|-------------------|---------------|
| JWT_SECRET | Every 3 months | `heroku config:set JWT_SECRET=$(openssl rand -hex 32)` <br>⚠️ Logs out all users |
| PAYSTACK_SECRET | Annually or if compromised | Generate new key in Paystack dashboard |
| BREVO_API_KEY | Annually or if compromised | Generate new key in Brevo dashboard |
| AWS_ACCESS_KEY | Every 6 months | Create new key in AWS IAM, update app, delete old |
| TWILIO_AUTH_TOKEN | Annually or if compromised | Generate new token in Twilio dashboard |

## Environment Variables Reference

### Core Application
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| DATABASE_URL | Yes | PostgreSQL connection string | `postgresql+psycopg2://user:pass@host/db` |
| REDIS_URL | Yes | Redis connection string | `redis://localhost:6379/0` |
| JWT_SECRET | Yes | Secret for JWT tokens (min 32 chars) | Random hex string |
| JWT_ALGORITHM | No | JWT signing algorithm | `HS256` (default) |
| ACCESS_TOKEN_EXPIRE_MINUTES | No | Token expiry time | `1440` (24 hours) |

### Payment Processing
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| PAYSTACK_SECRET | Yes | Paystack secret key | `sk_live_xxx` (prod) or `sk_test_xxx` (dev) |
| PAYSTACK_PUBLIC_KEY | Yes | Paystack public key | `pk_live_xxx` or `pk_test_xxx` |

### Email & Notifications
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| BREVO_API_KEY | Yes | Brevo/Sendinblue API key | `xkeysib-xxx` |
| BREVO_SENDER_EMAIL | Yes | Default sender email | `noreply@suoops.com` |
| BREVO_SENDER_NAME | No | Sender display name | `SuoOps` |
| TWILIO_ACCOUNT_SID | Yes | Twilio account SID | `ACxxxxx` |
| TWILIO_AUTH_TOKEN | Yes | Twilio auth token | Token string |
| TWILIO_WHATSAPP_FROM | Yes | WhatsApp sender number | `whatsapp:+14155238886` |

### File Storage
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| AWS_ACCESS_KEY_ID | Yes | AWS IAM access key | Key ID |
| AWS_SECRET_ACCESS_KEY | Yes | AWS IAM secret key | Secret string |
| AWS_S3_BUCKET_NAME | Yes | S3 bucket name | `suoops-production` |
| AWS_REGION | No | AWS region | `us-east-1` (default) |

### Frontend & CORS
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| FRONTEND_URL | Yes | Frontend base URL for CORS | `https://suoops.com` |

### Monitoring
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| SENTRY_DSN | No | Sentry error tracking DSN | `https://xxx@sentry.io/xxx` |
| ENVIRONMENT | No | Environment name | `development`, `staging`, `production` |
| LOG_LEVEL | No | Logging level | `INFO`, `DEBUG`, `WARNING` |

## Troubleshooting

### "Environment variable not set" error
```bash
# Check if variable exists
heroku config:get VARIABLE_NAME --app suoops-backend

# If missing, set it
heroku config:set VARIABLE_NAME=value --app suoops-backend

# Restart app
heroku restart --app suoops-backend
```

### Local development not working
```bash
# Verify .env file exists
ls -la .env

# Check if values are correct (no quotes needed)
cat .env

# Source the file
source .env

# Test database connection
python -c "from app.db.session import engine; print('Connected:', engine)"
```

### Production secrets exposed
1. **Immediately rotate all secrets:**
   ```bash
   heroku config:set JWT_SECRET=$(openssl rand -hex 32) --app suoops-backend
   heroku config:set PAYSTACK_SECRET=<new-key> --app suoops-backend
   # Rotate all other secrets
   ```

2. **Check git history:**
   ```bash
   git log --all --full-history -- "*/.env"
   ```

3. **If found in history, use BFG Repo-Cleaner:**
   ```bash
   bfg --delete-files .env
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   ```

4. **Force-push (only if necessary):**
   ```bash
   git push --force
   ```

## Audit Checklist

Run this quarterly:

- [ ] .env is in .gitignore
- [ ] No .env in git history
- [ ] Production uses Heroku Config Vars only
- [ ] Test keys used in development
- [ ] Secrets rotated in last 3 months
- [ ] No secrets in code or comments
- [ ] Team members using 1Password for secrets
- [ ] Backup of production secrets stored securely

---

**Last Updated**: November 22, 2025  
**Owner**: DevOps Team  
**Review Schedule**: Quarterly
