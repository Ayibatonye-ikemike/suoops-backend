#!/bin/bash
# SuoOps Database Backup Testing Script
# Purpose: Automated testing of Heroku Postgres backup procedures
# Schedule: Run monthly (1st of each month)
# Last Updated: November 21, 2025

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

APP_NAME="suoops-backend"
BACKUP_DIR="/tmp/suoops-backups"
TEST_REPORT="backup_test_report_$(date +%Y%m%d_%H%M%S).txt"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SuoOps Database Backup Test"
echo "  Date: $(date)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"
cd "$BACKUP_DIR"

# Start test report
echo "SuoOps Database Backup Test Report" > "$TEST_REPORT"
echo "Generated: $(date)" >> "$TEST_REPORT"
echo "========================================" >> "$TEST_REPORT"
echo "" >> "$TEST_REPORT"

# Test 1: Check Heroku CLI is installed
echo -e "${YELLOW}[Test 1/8]${NC} Checking Heroku CLI installation..."
if ! command -v heroku &> /dev/null; then
    echo -e "${RED}✗ FAILED${NC} - Heroku CLI not installed"
    echo "FAILED - Heroku CLI not installed" >> "$TEST_REPORT"
    exit 1
fi
echo -e "${GREEN}✓ PASSED${NC} - Heroku CLI installed"
echo "PASSED - Heroku CLI installed" >> "$TEST_REPORT"
echo ""

# Test 2: Check authentication
echo -e "${YELLOW}[Test 2/8]${NC} Checking Heroku authentication..."
if ! heroku auth:whoami &> /dev/null; then
    echo -e "${RED}✗ FAILED${NC} - Not authenticated with Heroku"
    echo "FAILED - Not authenticated with Heroku" >> "$TEST_REPORT"
    echo "Run: heroku login"
    exit 1
fi
HEROKU_USER=$(heroku auth:whoami)
echo -e "${GREEN}✓ PASSED${NC} - Authenticated as $HEROKU_USER"
echo "PASSED - Authenticated as $HEROKU_USER" >> "$TEST_REPORT"
echo ""

# Test 3: List existing backups
echo -e "${YELLOW}[Test 3/8]${NC} Checking existing backups..."
echo "Existing backups:" >> "$TEST_REPORT"
heroku pg:backups --app "$APP_NAME" | tee -a "$TEST_REPORT"

# Get backup count
BACKUP_COUNT=$(heroku pg:backups --app "$APP_NAME" | grep -c "^b" || echo "0")
echo ""
echo "Total backups found: $BACKUP_COUNT" | tee -a "$TEST_REPORT"

if [ "$BACKUP_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠ WARNING${NC} - No backups found. This is unusual."
    echo "WARNING - No existing backups found" >> "$TEST_REPORT"
else
    echo -e "${GREEN}✓ PASSED${NC} - Found $BACKUP_COUNT existing backup(s)"
    echo "PASSED - Found $BACKUP_COUNT existing backup(s)" >> "$TEST_REPORT"
fi
echo ""

# Test 4: Create manual backup
echo -e "${YELLOW}[Test 4/8]${NC} Creating manual backup..."
echo "Creating backup..." >> "$TEST_REPORT"

if heroku pg:backups:capture --app "$APP_NAME" >> "$TEST_REPORT" 2>&1; then
    echo -e "${GREEN}✓ PASSED${NC} - Manual backup created successfully"
    echo "PASSED - Manual backup created" >> "$TEST_REPORT"
else
    echo -e "${RED}✗ FAILED${NC} - Could not create backup"
    echo "FAILED - Backup creation failed" >> "$TEST_REPORT"
    exit 1
fi
echo ""

# Wait for backup to complete
echo "Waiting for backup to complete..."
sleep 10

# Test 5: Get latest backup info
echo -e "${YELLOW}[Test 5/8]${NC} Checking latest backup details..."
echo "Latest backup details:" >> "$TEST_REPORT"
BACKUP_INFO=$(heroku pg:backups:info --app "$APP_NAME")
echo "$BACKUP_INFO" | tee -a "$TEST_REPORT"

# Extract backup size
BACKUP_SIZE=$(echo "$BACKUP_INFO" | grep "Size" | awk '{print $2}')
echo ""
echo "Backup size: $BACKUP_SIZE" | tee -a "$TEST_REPORT"

if [ -z "$BACKUP_SIZE" ]; then
    echo -e "${RED}✗ FAILED${NC} - Could not determine backup size"
    echo "FAILED - Could not determine backup size" >> "$TEST_REPORT"
else
    echo -e "${GREEN}✓ PASSED${NC} - Backup size: $BACKUP_SIZE"
    echo "PASSED - Backup size verified" >> "$TEST_REPORT"
fi
echo ""

# Test 6: Download backup
echo -e "${YELLOW}[Test 6/8]${NC} Downloading backup..."
BACKUP_FILE="latest_$(date +%Y%m%d_%H%M%S).dump"

if heroku pg:backups:download --app "$APP_NAME" --output "$BACKUP_FILE" >> "$TEST_REPORT" 2>&1; then
    echo -e "${GREEN}✓ PASSED${NC} - Backup downloaded successfully"
    echo "PASSED - Backup downloaded as $BACKUP_FILE" >> "$TEST_REPORT"
else
    echo -e "${RED}✗ FAILED${NC} - Could not download backup"
    echo "FAILED - Backup download failed" >> "$TEST_REPORT"
    exit 1
fi
echo ""

# Test 7: Verify backup file
echo -e "${YELLOW}[Test 7/8]${NC} Verifying backup file integrity..."

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}✗ FAILED${NC} - Backup file not found"
    echo "FAILED - Backup file not found" >> "$TEST_REPORT"
    exit 1
fi

FILE_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "Downloaded file size: $FILE_SIZE" | tee -a "$TEST_REPORT"

# Check if file is larger than 1KB (valid backup should be substantial)
FILE_SIZE_BYTES=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null)

if [ "$FILE_SIZE_BYTES" -lt 1024 ]; then
    echo -e "${RED}✗ FAILED${NC} - Backup file too small ($FILE_SIZE). May be corrupted."
    echo "FAILED - Backup file too small" >> "$TEST_REPORT"
    exit 1
fi

echo -e "${GREEN}✓ PASSED${NC} - Backup file size valid: $FILE_SIZE"
echo "PASSED - Backup file integrity check" >> "$TEST_REPORT"
echo ""

# Test 8: Basic pg_restore validation
echo -e "${YELLOW}[Test 8/8]${NC} Validating backup structure..."

if command -v pg_restore &> /dev/null; then
    # List backup contents to verify it's a valid PostgreSQL dump
    if pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
        TABLE_COUNT=$(pg_restore --list "$BACKUP_FILE" | grep -c "TABLE DATA" || echo "0")
        echo "Tables found in backup: $TABLE_COUNT" | tee -a "$TEST_REPORT"
        
        if [ "$TABLE_COUNT" -gt 0 ]; then
            echo -e "${GREEN}✓ PASSED${NC} - Backup structure valid ($TABLE_COUNT tables)"
            echo "PASSED - Found $TABLE_COUNT tables in backup" >> "$TEST_REPORT"
        else
            echo -e "${YELLOW}⚠ WARNING${NC} - No tables found in backup"
            echo "WARNING - No tables found" >> "$TEST_REPORT"
        fi
    else
        echo -e "${RED}✗ FAILED${NC} - Backup file appears corrupted"
        echo "FAILED - pg_restore validation failed" >> "$TEST_REPORT"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ SKIPPED${NC} - pg_restore not installed, cannot validate structure"
    echo "SKIPPED - pg_restore not available" >> "$TEST_REPORT"
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Test Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Summary:" >> "$TEST_REPORT"
echo "========================================" >> "$TEST_REPORT"

PASSED_COUNT=$(grep -c "^PASSED" "$TEST_REPORT" || echo "0")
FAILED_COUNT=$(grep -c "^FAILED" "$TEST_REPORT" || echo "0")
WARNING_COUNT=$(grep -c "^WARNING" "$TEST_REPORT" || echo "0")
SKIPPED_COUNT=$(grep -c "^SKIPPED" "$TEST_REPORT" || echo "0")

echo -e "${GREEN}Passed:${NC} $PASSED_COUNT" | tee -a "$TEST_REPORT"
echo -e "${RED}Failed:${NC} $FAILED_COUNT" | tee -a "$TEST_REPORT"
echo -e "${YELLOW}Warnings:${NC} $WARNING_COUNT" | tee -a "$TEST_REPORT"
echo -e "Skipped: $SKIPPED_COUNT" | tee -a "$TEST_REPORT"
echo ""

echo "Backup location: $BACKUP_DIR/$BACKUP_FILE" | tee -a "$TEST_REPORT"
echo "Test report: $BACKUP_DIR/$TEST_REPORT" | tee -a "$TEST_REPORT"
echo ""

# Cleanup recommendation
echo -e "${YELLOW}Note:${NC} Backup files are stored locally in $BACKUP_DIR"
echo "To clean up old backups, run: rm -rf $BACKUP_DIR"
echo ""

# Next steps
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Next Steps"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Review test report: $BACKUP_DIR/$TEST_REPORT"
echo "2. Schedule monthly runs: Add to cron or CI/CD"
echo "3. Test restoration on staging environment"
echo "4. Document any issues in incident log"
echo ""

if [ "$FAILED_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
    echo ""
    echo "Backup procedures are working correctly! ✅"
    echo "ALL TESTS PASSED - Backup procedures verified" >> "$TEST_REPORT"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    echo "Please review failures and fix backup procedures."
    echo "TESTS FAILED - Review required" >> "$TEST_REPORT"
    exit 1
fi
