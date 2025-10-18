#!/bin/bash

# SuoPay Deployment Script
# This script helps deploy the backend to Heroku and frontend to Vercel

set -e

echo "🚀 SuoPay Deployment Script"
echo "============================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if required tools are installed
check_dependencies() {
    echo -e "${YELLOW}Checking dependencies...${NC}"
    
    if ! command -v heroku &> /dev/null; then
        echo -e "${RED}Error: Heroku CLI is not installed${NC}"
        echo "Please install it from: https://devcenter.heroku.com/articles/heroku-cli"
        exit 1
    fi
    
    if ! command -v vercel &> /dev/null; then
        echo -e "${RED}Error: Vercel CLI is not installed${NC}"
        echo "Please install it with: npm i -g vercel"
        exit 1
    fi
    
    if ! command -v git &> /dev/null; then
        echo -e "${RED}Error: Git is not installed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ All dependencies are installed${NC}"
}

# Deploy backend to Heroku
deploy_backend() {
    echo -e "${YELLOW}🔧 Deploying backend to Heroku...${NC}"
    
    # Check if logged in to Heroku
    if ! heroku auth:whoami &> /dev/null; then
        echo -e "${YELLOW}Please log in to Heroku first:${NC}"
        heroku auth:login
    fi
    
    # Create Heroku app if it doesn't exist
    read -p "Enter your Heroku app name for backend (e.g., suopay-backend): " HEROKU_APP_NAME
    
    if ! heroku apps:info $HEROKU_APP_NAME &> /dev/null; then
        echo "Creating Heroku app: $HEROKU_APP_NAME"
        heroku create $HEROKU_APP_NAME --region us
        
        # Add addons
        echo "Adding PostgreSQL addon..."
        heroku addons:create heroku-postgresql:mini -a $HEROKU_APP_NAME
        
        echo "Adding Redis addon..."
        heroku addons:create heroku-redis:mini -a $HEROKU_APP_NAME
    fi
    
    # Set environment variables
    echo "Setting environment variables..."
    heroku config:set ENV=prod -a $HEROKU_APP_NAME
    heroku config:set APP_NAME=SuoPay -a $HEROKU_APP_NAME
    
    # You'll need to set these manually with your actual values
    echo -e "${YELLOW}⚠️  Please set the following environment variables manually:${NC}"
    echo "heroku config:set WHATSAPP_API_KEY=your_whatsapp_token -a $HEROKU_APP_NAME"
    echo "heroku config:set PAYSTACK_SECRET=your_paystack_secret -a $HEROKU_APP_NAME"
    echo "heroku config:set FLUTTERWAVE_SECRET=your_flutterwave_secret -a $HEROKU_APP_NAME"
    echo "heroku config:set S3_ACCESS_KEY=your_s3_access_key -a $HEROKU_APP_NAME"
    echo "heroku config:set S3_SECRET_KEY=your_s3_secret_key -a $HEROKU_APP_NAME"
    echo "heroku config:set S3_BUCKET=suopay-storage -a $HEROKU_APP_NAME"
    
    # Deploy
    echo "Deploying to Heroku..."
    git push heroku main
    
    echo -e "${GREEN}✅ Backend deployed successfully!${NC}"
    echo "Backend URL: https://$HEROKU_APP_NAME.herokuapp.com"
}

# Deploy frontend to Vercel
deploy_frontend() {
    echo -e "${YELLOW}🎨 Deploying frontend to Vercel...${NC}"
    
    cd frontend
    
    # Install dependencies
    echo "Installing frontend dependencies..."
    npm install
    
    # Deploy to Vercel
    echo "Deploying to Vercel..."
    vercel --prod
    
    cd ..
    
    echo -e "${GREEN}✅ Frontend deployed successfully!${NC}"
}

# Main deployment flow
main() {
    check_dependencies
    
    echo ""
    echo "What would you like to deploy?"
    echo "1) Backend only"
    echo "2) Frontend only"
    echo "3) Both backend and frontend"
    read -p "Enter your choice (1-3): " choice
    
    case $choice in
        1)
            deploy_backend
            ;;
        2)
            deploy_frontend
            ;;
        3)
            deploy_backend
            echo ""
            deploy_frontend
            ;;
        *)
            echo -e "${RED}Invalid choice. Please run the script again.${NC}"
            exit 1
            ;;
    esac
    
    echo ""
    echo -e "${GREEN}🎉 Deployment completed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Set up your custom domain suopay.io in Vercel dashboard"
    echo "2. Update CORS settings in backend with your frontend domain"
    echo "3. Configure your payment provider webhooks"
    echo "4. Set up monitoring and logging"
}

main "$@"