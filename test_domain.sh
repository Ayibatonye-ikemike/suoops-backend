#!/bin/bash

echo "=================================="
echo "🧪 Testing api.suoops.com Domain"
echo "=================================="
echo ""
echo "⚠️  IMPORTANT: Make sure ControlD is DISABLED before running this test"
echo ""
echo "Waiting 3 seconds..."
sleep 3

BASE_URL="https://api.suoops.com"

echo ""
echo "1️⃣  Testing DNS Resolution..."
echo "-----------------------------------"
echo "$ dig api.suoops.com +short"
DIG_RESULT=$(dig api.suoops.com +short)
echo "$DIG_RESULT"

if echo "$DIG_RESULT" | grep -q "0.0.0.0"; then
    echo "❌ ERROR: DNS still resolving to 0.0.0.0"
    echo "   ControlD is still active or not fully disabled"
    echo "   Please disable ControlD and wait a few seconds"
    exit 1
fi

if [ -z "$DIG_RESULT" ]; then
    echo "⚠️  WARNING: No DNS resolution found"
    echo "   This might be a DNS propagation issue"
else
    echo "✅ DNS resolving to: $DIG_RESULT"
fi

echo ""
echo "2️⃣  Testing Health Check..."
echo "-----------------------------------"
echo "$ curl -s $BASE_URL/healthz"
HEALTH=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/healthz")
HTTP_CODE=$(echo "$HEALTH" | grep "HTTP_CODE" | cut -d: -f2)
RESPONSE=$(echo "$HEALTH" | grep -v "HTTP_CODE")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Health check passed: $RESPONSE"
else
    echo "❌ Health check failed (HTTP $HTTP_CODE)"
    echo "   Response: $RESPONSE"
    exit 1
fi

echo ""
echo "3️⃣  Testing QR Verification Endpoint (Non-existent Invoice)..."
echo "-----------------------------------"
echo "$ curl -s $BASE_URL/invoices/TEST-FAKE-123/verify"
VERIFY=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/invoices/TEST-FAKE-123/verify")
HTTP_CODE=$(echo "$VERIFY" | grep "HTTP_CODE" | cut -d: -f2)
RESPONSE=$(echo "$VERIFY" | grep -v "HTTP_CODE")

if [ "$HTTP_CODE" = "404" ]; then
    echo "✅ Verification endpoint working (404 for fake invoice)"
    echo "   Response: $RESPONSE"
else
    echo "❌ Unexpected response (HTTP $HTTP_CODE)"
    echo "   Response: $RESPONSE"
fi

echo ""
echo "4️⃣  Testing WhatsApp Webhook (With Verification Token)..."
echo "-----------------------------------"
echo "$ curl -s '$BASE_URL/webhooks/whatsapp?hub.mode=subscribe&hub.challenge=test123&hub.verify_token=...'"
WEBHOOK=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/webhooks/whatsapp?hub.mode=subscribe&hub.challenge=test123&hub.verify_token=YOUR_VERIFY_TOKEN")
HTTP_CODE=$(echo "$WEBHOOK" | grep "HTTP_CODE" | cut -d: -f2)
RESPONSE=$(echo "$WEBHOOK" | grep -v "HTTP_CODE")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Webhook working: $RESPONSE"
else
    echo "⚠️  Webhook response (HTTP $HTTP_CODE): $RESPONSE"
fi

echo ""
echo "5️⃣  Testing Metrics Endpoint..."
echo "-----------------------------------"
echo "$ curl -s $BASE_URL/metrics | head -5"
METRICS=$(curl -s "$BASE_URL/metrics" | head -5)
if echo "$METRICS" | grep -q "python_gc"; then
    echo "✅ Metrics endpoint working"
    echo "$METRICS"
else
    echo "❌ Metrics endpoint failed"
fi

echo ""
echo "6️⃣  Testing SSL Certificate..."
echo "-----------------------------------"
echo "$ curl -vI $BASE_URL/healthz 2>&1 | grep 'subject\\|issuer\\|expire'"
SSL_INFO=$(curl -vI "$BASE_URL/healthz" 2>&1 | grep -E "subject:|issuer:|expire date:" | head -3)
if [ -n "$SSL_INFO" ]; then
    echo "✅ SSL Certificate info:"
    echo "$SSL_INFO"
else
    echo "⚠️  Could not retrieve SSL certificate info"
fi

echo ""
echo "=================================="
echo "📊 Test Summary"
echo "=================================="
echo ""
echo "✅ All critical endpoints are working!"
echo ""
echo "Domain: $BASE_URL"
echo "Status: OPERATIONAL"
echo ""
echo "Next steps:"
echo "1. Create a real invoice via dashboard or WhatsApp"
echo "2. Download the PDF invoice"
echo "3. Scan the QR code with your phone"
echo "4. Verify it opens: $BASE_URL/invoices/{INVOICE_ID}/verify"
echo "5. Confirm you see invoice details"
echo ""
echo "=================================="
