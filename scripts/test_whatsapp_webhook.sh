#!/bin/bash
# Test WhatsApp webhook with mock payload

echo "🧪 Testing WhatsApp Webhook - Three-Way Flow"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Heroku app URL
BASE_URL="https://suopay-backend-a204d4816960.herokuapp.com"

echo "Step 1: Test Webhook Verification (GET request)"
echo "------------------------------------------------"
VERIFICATION=$(curl -s -X GET "$BASE_URL/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=suopay_verify_2025&hub.challenge=test_challenge_123")

if [ "$VERIFICATION" = "test_challenge_123" ]; then
    echo -e "${GREEN}✅ Webhook verification successful!${NC}"
    echo "   Response: $VERIFICATION"
else
    echo -e "${RED}❌ Webhook verification failed!${NC}"
    echo "   Response: $VERIFICATION"
    exit 1
fi

echo ""
echo "Step 2: Send Mock Text Message (POST request)"
echo "----------------------------------------------"
echo -e "${YELLOW}Simulating: Business +2348012345678 sends message${NC}"
echo "Message: 'Invoice Jane Doe +2348087654321 50000 for logo design'"
echo ""

# Mock WhatsApp text message payload
TEXT_PAYLOAD='{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "713163545130337",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "15550123456",
          "phone_number_id": "817255254808254"
        },
        "contacts": [{
          "profile": {"name": "Mike Business"},
          "wa_id": "2348012345678"
        }],
        "messages": [{
          "from": "2348012345678",
          "id": "wamid.HBgNMjM0ODAxMjM0NTY3OBUCABIYIDNBMzQwNzE5RjQxNEE0",
          "timestamp": "1698432000",
          "text": {
            "body": "Invoice Jane Doe +2348087654321 50000 for logo design and branding"
          },
          "type": "text"
        }]
      },
      "field": "messages"
    }]
  }]
}'

TEXT_RESPONSE=$(curl -s -X POST "$BASE_URL/webhooks/whatsapp" \
  -H "Content-Type: application/json" \
  -d "$TEXT_PAYLOAD")

echo "Response: $TEXT_RESPONSE"

if echo "$TEXT_RESPONSE" | grep -q '"ok":true'; then
    echo -e "${GREEN}✅ Message received and queued!${NC}"
else
    echo -e "${RED}❌ Message processing failed!${NC}"
    exit 1
fi

echo ""
echo "Step 3: Check Celery Worker Logs"
echo "---------------------------------"
echo -e "${YELLOW}Checking if Celery worker processed the message...${NC}"
echo ""

# Wait a bit for Celery to process
sleep 3

# Check logs
echo "Recent logs:"
heroku logs --tail --num 50 --source app | grep -E "whatsapp|invoice|celery" | tail -15

echo ""
echo "=============================================="
echo -e "${GREEN}🎉 Test Complete!${NC}"
echo ""
echo "What should have happened:"
echo "1. ✅ Webhook verified with Meta"
echo "2. ✅ Message received and queued for Celery"
echo "3. 🔄 Celery worker processes message:"
echo "   • Identifies business by phone (+2348012345678)"
echo "   • Extracts customer phone (+2348087654321)"
echo "   • Creates invoice for ₦50,000"
echo "   • Sends confirmation to business"
echo "   • Sends invoice to customer"
echo ""
echo "Next: Check logs above to confirm Celery processing"
echo "     heroku logs --tail | grep whatsapp"
