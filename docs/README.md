# SuoOps Documentation

This directory contains public-facing documentation for SuoOps platform features and provisional fiscalization readiness (FIRS accreditation pending – no live external gateway integration yet). Any former references to NRS registration are historical and will be phased out; external compliance claims are forward-looking only.

## Files

1. **api-documentation.html** - Complete API reference with authentication, endpoints, rate limits, error handling
2. **service-level-agreement.html** - SLA commitments covering uptime, performance, security, support

## Deployment to Public URL

### Option 1: GitHub Pages (Lightweight Public Hosting)

```bash
# 1. Create docs branch
git checkout -b gh-pages

# 2. Copy documentation files to root
cp docs/api-documentation.html index.html
cp docs/service-level-agreement.html sla.html

# 3. Create simple index page (optional)
cat > landing.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>SuoOps Documentation</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: system-ui; max-width: 600px; margin: 100px auto; text-align: center; }
        a { display: block; margin: 20px; padding: 20px; background: #667eea; color: white; text-decoration: none; border-radius: 8px; }
    </style>
</head>
<body>
    <h1>SuoOps Documentation</h1>
    <a href="index.html">API Documentation</a>
    <a href="sla.html">Service Level Agreement</a>
</body>
</html>
EOF

# 4. Push to GitHub
git add .
git commit -m "docs: Deploy documentation to GitHub Pages"
git push origin gh-pages

# 5. Enable GitHub Pages in repository settings
# Settings → Pages → Source: gh-pages branch → Save
```

**Public URLs will be:**
- API Docs: `https://yourusername.github.io/suopay.io/index.html`
- SLA: `https://yourusername.github.io/suopay.io/sla.html`

### Option 2: Vercel (with Custom Domain)

```bash
# 1. Create vercel.json in docs/
cat > docs/vercel.json << 'EOF'
{
  "cleanUrls": true,
  "trailingSlash": false,
  "routes": [
    { "src": "/api", "dest": "/api-documentation.html" },
    { "src": "/sla", "dest": "/service-level-agreement.html" }
  ]
}
EOF

# 2. Deploy docs directory
cd docs
vercel --prod

# 3. Custom domain (optional)
# Vercel Dashboard → Project → Settings → Domains → Add "docs.suoops.com"
```

**Public URLs will be:**
- API Docs: `https://your-project.vercel.app/api`
- SLA: `https://your-project.vercel.app/sla`
- Or with custom domain: `https://docs.suoops.com/api` and `https://docs.suoops.com/sla`

### Option 3: AWS S3 + CloudFront (Enterprise)

```bash
# 1. Create S3 bucket
aws s3 mb s3://docs.suoops.com

# 2. Upload files
aws s3 sync docs/ s3://docs.suoops.com --acl public-read

# 3. Enable static website hosting
aws s3 website s3://docs.suoops.com --index-document api-documentation.html

# 4. Create CloudFront distribution (optional, for CDN)
aws cloudfront create-distribution --origin-domain-name docs.suoops.com.s3-website-us-east-1.amazonaws.com
```

## Accreditation & External Integration (Forward-Looking)

Public URLs (API docs, SLA) will support future accreditation submissions. Until FIRS accreditation is granted, they represent provisional capabilities only:

1. **API Documentation URL:** `https://docs.suoops.com/api`
2. **SLA Document URL:** `https://docs.suoops.com/sla`
3. **(Optional)** Privacy/Security Policy URLs (to be added pre-accreditation)

## Local Testing

```bash
# Serve locally on port 8000
cd docs
python3 -m http.server 8000

# Open in browser:
# http://localhost:8000/api-documentation.html
# http://localhost:8000/service-level-agreement.html
```

## Maintenance

- **Updates:** Edit HTML files directly, redeploy using chosen method
- **Versioning:** Include version number and date in footer (already added)
- **Compliance:** Review quarterly for evolving FIRS e-invoicing guidance
- **Feedback:** Send updates to support@suoops.com

## Security Notes

- ✅ No sensitive data in public docs
- ✅ API keys shown as examples only (`sk_test_...`)
- ✅ Contact information uses placeholders (+234-xxx-xxx-xxxx)
- ✅ All examples use test data

## Next Steps

1. ✅ Documentation created (api-documentation.html, service-level-agreement.html)
2. ⏳ Deploy to public URL using one of the methods above
3. ⏳ Prepare accreditation dossier (architecture, security, SLA) – pending
4. ⏳ Add actual phone numbers and support emails before production
5. ⏳ Add privacy & security policy pages (pre-accreditation)

---
DISCLAIMER: Documentation describes provisional fiscalization readiness. No live external regulatory transmission occurs until accreditation approval; all gateway references are roadmap items.
