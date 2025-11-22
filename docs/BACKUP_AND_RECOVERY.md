# SuoOps Backup and Recovery Procedures

## Overview
SuoOps uses Heroku Postgres with automated daily backups. This document outlines backup procedures, disaster recovery process, and testing schedules.

## Current Backup Configuration

### Automated Backups (Heroku)
- **Frequency**: Daily automatic backups
- **Retention**: 7 days (Standard/Premium plans)
- **Backup Time**: Approximately 02:00 UTC
- **Storage**: Encrypted AWS S3 (managed by Heroku)

### Backup Commands

**Create manual backup:**
```bash
heroku pg:backups:capture --app suoops-backend
```

**List all backups:**
```bash
heroku pg:backups --app suoops-backend
```

**Download backup:**
```bash
heroku pg:backups:download --app suoops-backend
# Creates latest.dump file
```

**Restore from backup:**
```bash
# Restore from latest backup
heroku pg:backups:restore --app suoops-backend

# Restore from specific backup
heroku pg:backups:restore b001 --app suoops-backend
```

## Disaster Recovery Procedures

### Scenario 1: Database Corruption
**Detection**: Application errors, data inconsistencies, Sentry alerts

**Response Steps:**
1. Immediately create manual backup of current state:
   ```bash
   heroku pg:backups:capture --app suoops-backend
   ```

2. Assess corruption extent by checking recent database logs:
   ```bash
   heroku logs --tail --ps postgres --app suoops-backend
   ```

3. If corruption is recent (< 24 hours), restore from previous day:
   ```bash
   heroku pg:backups:restore b001 --app suoops-backend --confirm suoops-backend
   ```

4. Verify restoration:
   ```bash
   heroku run python -c "from app.db.session import engine; print('Tables:', engine.table_names())" --app suoops-backend
   ```

5. Test critical flows (login, invoice creation, payment)

**Expected Recovery Time**: 30-60 minutes

### Scenario 2: Accidental Data Deletion
**Detection**: User reports missing data, admin audit

**Response Steps:**
1. Identify deletion timestamp from logs
2. Export affected tables from latest backup:
   ```bash
   heroku pg:backups:download --app suoops-backend
   pg_restore -d postgres://localhost/suoops_recovery -t invoices latest.dump
   ```

3. Extract deleted records and merge back
4. Verify data integrity
5. Document incident for post-mortem

**Expected Recovery Time**: 1-2 hours

### Scenario 3: Complete Application Failure
**Detection**: 100% error rate, application unreachable

**Response Steps:**
1. Check Heroku status: https://status.heroku.com
2. Review recent deployments:
   ```bash
   heroku releases --app suoops-backend
   ```

3. Rollback if caused by bad deploy:
   ```bash
   heroku rollback --app suoops-backend
   ```

4. If database issue, restore from last known good backup
5. Scale up dynos if resource exhaustion:
   ```bash
   heroku ps:scale web=2 --app suoops-backend
   ```

**Expected Recovery Time**: 15-30 minutes

## Point-in-Time Recovery (PITR)

Heroku Postgres supports PITR for Standard and Premium plans.

**Enable PITR:**
```bash
heroku pg:backups:schedule DATABASE_URL --at '02:00 UTC' --app suoops-backend
```

**Restore to specific time:**
```bash
# Restore to 6 hours ago
heroku pg:backups:restore --app suoops-backend --to-timestamp '6 hours ago'
```

## Backup Testing Schedule

### Monthly Testing (1st of each month)
- Download latest backup
- Restore to staging environment
- Run smoke tests on critical endpoints
- Verify invoice PDFs accessible
- Document test results

**Test Checklist:**
- [ ] Backup downloads successfully
- [ ] Restore completes without errors
- [ ] User authentication works
- [ ] Invoice creation works
- [ ] Payment status updates work
- [ ] PDF generation works
- [ ] Email notifications work

### Quarterly DR Drill (Every 3 months)
- Simulate complete database failure
- Perform full restoration procedure
- Measure actual recovery time
- Update procedures based on findings
- Train team on recovery process

## Backup Verification

**Check backup integrity:**
```bash
# Verify backup exists and is recent
heroku pg:backups:info --app suoops-backend

# Expected output shows backup < 24 hours old
```

**Monitor backup status:**
```bash
# Set up daily backup monitoring
heroku pg:backups:schedules --app suoops-backend
```

## Recovery Time Objectives (RTO) and Recovery Point Objectives (RPO)

| Scenario | RTO (Max Downtime) | RPO (Max Data Loss) |
|----------|-------------------|---------------------|
| Database corruption | 60 minutes | 24 hours |
| Accidental deletion | 2 hours | 24 hours |
| Complete failure | 30 minutes | 24 hours |
| Heroku outage | 4 hours | 24 hours |

## Escalation Contacts

**Technical Issues:**
- Primary: Technical Lead
- Secondary: DevOps Engineer
- Heroku Support: https://help.heroku.com

**Business Impact:**
- Notify: Product Owner
- Communication: Customer Support Team

## Post-Incident Review

After any recovery event:
1. Document timeline of events
2. Identify root cause
3. Update procedures if needed
4. Schedule team debrief within 48 hours
5. Update monitoring/alerts to prevent recurrence

## Backup Retention Policy

| Backup Type | Retention Period | Storage Location |
|-------------|-----------------|------------------|
| Daily automatic | 7 days | Heroku (AWS S3) |
| Manual snapshots | 30 days | Heroku (AWS S3) |
| Monthly archives | 1 year | External S3 bucket |
| Critical milestones | Indefinite | Secure archive |

## Additional Backup Recommendations

### External Backup Strategy (Future Enhancement)
1. Set up weekly exports to external S3 bucket
2. Automate with Heroku Scheduler:
   ```bash
   heroku pg:backups:download --app suoops-backend
   aws s3 cp latest.dump s3://suoops-backups/$(date +%Y%m%d).dump
   ```

3. Encrypt backups at rest and in transit
4. Implement backup monitoring alerts

### Data Export for Compliance
Monthly export of critical data:
- All invoices (PDF + database records)
- User data (GDPR compliance)
- Audit logs
- Financial transactions

## Emergency Contact Information

**Heroku Support:**
- Email: support@heroku.com
- Phone: +1 (415) 636-1399
- Status: https://status.heroku.com

**AWS Support (S3 backups):**
- Console: https://console.aws.amazon.com
- Support: Through AWS Console

## Review and Update Schedule

This document should be reviewed and updated:
- After each DR test
- After any recovery event
- Quarterly as part of security review
- When infrastructure changes

**Last Updated**: November 21, 2025
**Next Review**: February 21, 2026
**Document Owner**: Technical Lead
