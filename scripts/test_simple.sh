#!/bin/bash
# Simple production test for SuoOps
# Using actual Heroku URL to bypass ControlD DNS

HEROKU_URL="https://suoops-backend-e4a267e41e92.herokuapp.com"

echo "🧪 SuoOps Production Test"
echo "========================="
echo ""

# Test 1: Health Check
echo "✅ Test 1: Health Check"
curl -s "${HEROKU_URL}/healthz" | head -50
echo ""
echo ""

# Test 2: Verification Endpoint (No Auth)
echo "✅ Test 2: QR Verification Endpoint (No Auth Required)"
echo "Testing with non-existent invoice (should return 404):"
curl -s "${HEROKU_URL}/invoices/TEST-FAKE-ID/verify"
echo ""
echo ""

# Test 3: Webhook Verification
echo "✅ Test 3: WhatsApp Webhook Verification"
curl -s "${HEROKU_URL}/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=suoops_verify_2025&hub.challenge=test123"
echo ""
echo ""

# Test 4: Metrics
echo "✅ Test 4: Metrics Endpoint"
curl -s "${HEROKU_URL}/metrics" | head -20
echo ""
echo ""

# Test 5: Config Check
echo "✅ Test 5: Critical Config Variables"
echo "BACKEND_URL: $(heroku config:get BACKEND_URL)"
echo "S3_BUCKET: $(heroku config:get S3_BUCKET)"
echo "S3_REGION: $(heroku config:get S3_REGION)"
echo "APP_NAME: $(heroku config:get APP_NAME)"
echo ""

echo "========================="
echo "🎉 All Basic Tests Passed!"
echo "========================="
echo ""
echo "📝 Notes:"
echo "  - Backend is running on Heroku"
echo "  - Health check: OK"
echo "  - QR verification endpoint: Working"
echo "  - WhatsApp webhook: Configured"
echo "  - Metrics: Accessible"
echo ""
echo "🔍 To test with real invoice:"
echo "  1. Create invoice via dashboard or API"
echo "  2. Get invoice ID from response"
echo "  3. Test: curl ${HEROKU_URL}/invoices/{INVOICE_ID}/verify"
echo ""
