#!/bin/bash
# Test WhatsApp webhook with mock payload

set -euo pipefail

echo "🧪 Testing WhatsApp Webhook - Three-Way Flow"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Defaults (can be overridden via flags or env vars)
BASE_URL="${BASE_URL:-https://suoops-backend.herokuapp.com}"
BUSINESS_PHONE="${BUSINESS_PHONE:-2348012345678}"
CUSTOMER_PHONE="${CUSTOMER_PHONE:-2348087654321}"
CUSTOMER_NAME="${CUSTOMER_NAME:-Jane Doe}"
AMOUNT_NAIRA="${AMOUNT_NAIRA:-50000}"
HEROKU_APP="${HEROKU_APP:-suoops-backend-a204d4816960}"
SLEEP_SECONDS="${SLEEP_SECONDS:-5}"

usage() {
    cat <<USAGE
Usage: $0 [options]

Options:
  --business-phone <number>   Business WhatsApp phone (default: ${BUSINESS_PHONE})
  --customer-phone <number>   Customer WhatsApp phone (default: ${CUSTOMER_PHONE})
  --customer-name <name>      Customer name (default: ${CUSTOMER_NAME})
  --amount <naira>            Invoice amount in naira (default: ${AMOUNT_NAIRA})
  --base-url <url>            Backend base URL (default: ${BASE_URL})
  --heroku-app <app>          Heroku app name for logs (default: ${HEROKU_APP})
  --sleep <seconds>           Wait time before fetching logs (default: ${SLEEP_SECONDS})
  --help                      Show this help message

Environment overrides:
  BASE_URL, BUSINESS_PHONE, CUSTOMER_PHONE, CUSTOMER_NAME, AMOUNT_NAIRA,
  HEROKU_APP, SLEEP_SECONDS

Example:
  BUSINESS_PHONE=2347065730703 CUSTOMER_PHONE=2348020000000 \
    $0 --customer-name "Jane Smith" --amount 75000
USAGE
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --business-phone)
            BUSINESS_PHONE="$2"; shift 2 ;;
        --customer-phone)
            CUSTOMER_PHONE="$2"; shift 2 ;;
        --customer-name)
            CUSTOMER_NAME="$2"; shift 2 ;;
        --amount)
            AMOUNT_NAIRA="$2"; shift 2 ;;
        --base-url)
            BASE_URL="$2"; shift 2 ;;
        --heroku-app)
            HEROKU_APP="$2"; shift 2 ;;
        --sleep)
            SLEEP_SECONDS="$2"; shift 2 ;;
        --help|-h)
            usage
            exit 0 ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1 ;;
    esac
done

echo "Configuration"
echo "-------------"
echo "Backend URL      : $BASE_URL"
echo "Business phone   : +$BUSINESS_PHONE"
echo "Customer phone   : +$CUSTOMER_PHONE"
echo "Customer name    : $CUSTOMER_NAME"
echo "Amount (naira)   : ₦$AMOUNT_NAIRA"
echo "Heroku app       : $HEROKU_APP"
echo "Log wait (sec)   : $SLEEP_SECONDS"
echo ""

echo "Step 1: Test Webhook Verification (GET request)"
echo "------------------------------------------------"
VERIFY_TOKEN=${WHATSAPP_VERIFY_TOKEN:-"set_your_verify_token"}
VERIFICATION=$(curl -s -X GET "$BASE_URL/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=${VERIFY_TOKEN}&hub.challenge=test_challenge_123")

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
echo -e "${YELLOW}Simulating: Business +$BUSINESS_PHONE sends invoice command${NC}"
MESSAGE_BODY="Invoice ${CUSTOMER_NAME} +${CUSTOMER_PHONE} ${AMOUNT_NAIRA} for logo design and branding"
echo "Message: '$MESSAGE_BODY'"
echo ""

# Mock WhatsApp text message payload
TEXT_PAYLOAD=$(cat <<JSON
{
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
          "profile": {"name": "Test Business"},
          "wa_id": "$BUSINESS_PHONE"
        }],
        "messages": [{
          "from": "$BUSINESS_PHONE",
          "id": "wamid.HBgNMjM0ODAxMjM0NTY3OBUCABIYIDNBMzQwNzE5RjQxNEE0",
          "timestamp": "1698432000",
          "text": {
            "body": "$MESSAGE_BODY"
          },
          "type": "text"
        }]
      },
      "field": "messages"
    }]
  }]
}
JSON
)

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
echo -e "${YELLOW}Waiting ${SLEEP_SECONDS}s for Celery processing...${NC}"
sleep "$SLEEP_SECONDS"

LOG_FILTER="whatsapp|invoice|celery|Generated invoice"
echo "Recent logs (filtered by: $LOG_FILTER):"
if ! heroku logs --app "$HEROKU_APP" --num 200 --source app 2>/dev/null | grep -E "$LOG_FILTER" | tail -20; then
    echo -e "${RED}⚠️  Unable to fetch Heroku logs. Ensure the Heroku CLI is authenticated and app name is correct.${NC}"
fi

echo ""
echo "=============================================="
echo -e "${GREEN}🎉 Test Complete!${NC}"
echo ""
echo "What should have happened:"
echo "1. ✅ Webhook verified with Meta"
echo "2. ✅ Message received and queued for Celery"
echo "3. 🔄 Celery worker processes message:"
echo "   • Identifies business by phone (+$BUSINESS_PHONE)"
echo "   • Extracts customer phone (+$CUSTOMER_PHONE)"
echo "   • Creates invoice for ₦$AMOUNT_NAIRA"
echo "   • Sends confirmation to business"
echo "   • Sends invoice to customer"
echo ""
echo "Tip: Adjust defaults by passing flags or setting env vars (see --help)."
