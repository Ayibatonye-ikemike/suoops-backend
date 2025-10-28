#!/bin/bash

# SuoPay Production Testing Script
echo "🧪 Testing SuoPay Production Setup..."
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_URL="https://api.suoops.com"

echo -e "${BLUE}Step 1: Test Health Endpoint${NC}"
curl -s "$API_URL/healthz" | jq .
echo ""

echo -e "${BLUE}Step 2: Login (Get Access Token)${NC}"
echo "Please provide your credentials:"
read -p "Phone (+2348XXXXXXXXX): " PHONE
read -sp "Password: " PASSWORD
echo ""

LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"$PHONE\",\"password\":\"$PASSWORD\"}")

ACCESS_TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo -e "${YELLOW}⚠️  Login failed. Please register first:${NC}"
  echo "curl -X POST $API_URL/auth/register \\"
  echo "  -H \"Content-Type: application/json\" \\"
  echo "  -d '{\"phone\":\"$PHONE\",\"name\":\"Your Name\",\"password\":\"$PASSWORD\"}'"
  exit 1
fi

echo -e "${GREEN}✅ Login successful!${NC}"
echo "Access Token: ${ACCESS_TOKEN:0:20}..."
echo ""

echo -e "${BLUE}Step 3: Create Invoice with Email${NC}"
read -p "Customer Name: " CUSTOMER_NAME
read -p "Customer Email: " CUSTOMER_EMAIL
read -p "Amount (NGN): " AMOUNT

INVOICE_RESPONSE=$(curl -s -X POST "$API_URL/invoices" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"customer_name\": \"$CUSTOMER_NAME\",
    \"customer_email\": \"$CUSTOMER_EMAIL\",
    \"amount\": $AMOUNT,
    \"lines\": [{
      \"description\": \"Test Service\",
      \"quantity\": 1,
      \"unit_price\": $AMOUNT
    }]
  }")

INVOICE_ID=$(echo $INVOICE_RESPONSE | jq -r '.invoice_id')

if [ "$INVOICE_ID" != "null" ] && [ -n "$INVOICE_ID" ]; then
  echo -e "${GREEN}✅ Invoice created: $INVOICE_ID${NC}"
  echo "PDF URL: $(echo $INVOICE_RESPONSE | jq -r '.pdf_url')"
  echo ""
  echo -e "${GREEN}✅ Email sent to: $CUSTOMER_EMAIL${NC}"
  echo "Check the inbox (and spam folder) for the invoice email!"
else
  echo -e "${YELLOW}⚠️  Failed to create invoice${NC}"
  echo $INVOICE_RESPONSE | jq .
fi

echo ""
echo -e "${BLUE}Step 4: Test Subscription Flow${NC}"
echo "Visit your dashboard to test:"
echo "1. Go to Settings → Subscription Plan"
echo "2. Click 'Upgrade Plan'"
echo "3. Select STARTER (₦2,500)"
echo "4. Use Paystack test card:"
echo "   Card: 5060 6666 6666 6666 123"
echo "   CVV: 123, PIN: 1234"
echo ""

echo -e "${GREEN}🎉 Production setup complete!${NC}"
