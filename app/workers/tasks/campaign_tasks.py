"""
Marketing Campaign Tasks.

Celery tasks for sending marketing campaigns asynchronously.
This allows sending to hundreds of users without hitting worker timeouts.
"""
from __future__ import annotations

import logging
from typing import Any

from celery import Task

from app.db.session import session_scope
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="campaign.send_bulk",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=600,  # 10 minute soft limit
    time_limit=660,  # 11 minute hard limit
)
def send_campaign_async(
    self: Task,
    campaign_type: str,
    dry_run: bool = True,
    limit: int = 100,
    admin_email: str = "system",
) -> dict[str, Any]:
    """
    Send marketing campaign asynchronously.
    
    This task runs in a Celery worker with extended timeout,
    allowing sending to hundreds of users without hitting web worker limits.
    
    Args:
        campaign_type: The campaign type value (e.g., "email_whatsapp_promotion")
        dry_run: If True, only log what would be sent
        limit: Maximum number of users to send to
        admin_email: Email of admin who initiated the campaign
    
    Returns:
        Campaign results dict with sent/failed/skipped counts
    """
    from app.services.marketing_campaigns import (
        CampaignType,
        MarketingCampaignService,
    )
    
    logger.info(
        "[CAMPAIGN_TASK] Starting %s campaign (dry_run=%s, limit=%d) initiated by %s",
        campaign_type, dry_run, limit, admin_email
    )
    
    try:
        campaign_enum = CampaignType(campaign_type)
    except ValueError:
        error_msg = f"Invalid campaign type: {campaign_type}"
        logger.error("[CAMPAIGN_TASK] %s", error_msg)
        return {
            "success": False,
            "error": error_msg,
            "campaign": campaign_type,
        }
    
    try:
        with session_scope() as db:
            service = MarketingCampaignService(db)
            result = service.send_campaign(
                campaign_type=campaign_enum,
                dry_run=dry_run,
                limit=limit,
            )
        
        logger.info(
            "[CAMPAIGN_TASK] %s complete: sent=%d, failed=%d, skipped=%d",
            campaign_type, result.get("sent", 0), result.get("failed", 0), result.get("skipped", 0)
        )
        
        return {
            "success": True,
            "task_id": self.request.id,
            **result,
        }
    except Exception as e:
        logger.exception("[CAMPAIGN_TASK] Failed to send %s campaign: %s", campaign_type, e)
        return {
            "success": False,
            "error": str(e),
            "campaign": campaign_type,
            "task_id": self.request.id,
        }


@celery_app.task(
    bind=True,
    name="campaign.send_single_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_single_email_async(
    self: Task,
    user_id: int,
    campaign_type: str,
) -> dict[str, Any]:
    """
    Send a single email to a user asynchronously.
    
    Useful for individual sends without blocking the web worker.
    
    Args:
        user_id: The user's ID
        campaign_type: The campaign type value
    
    Returns:
        Result dict with success status
    """
    from app.models.models import User
    from app.services.marketing_campaigns import (
        CampaignType,
        MarketingCampaignService,
        EMAIL_CAMPAIGNS,
    )
    
    logger.info("[CAMPAIGN_TASK] Sending single email to user %d, campaign=%s", user_id, campaign_type)
    
    try:
        campaign_enum = CampaignType(campaign_type)
        
        if campaign_enum not in EMAIL_CAMPAIGNS:
            return {
                "success": False,
                "error": f"{campaign_type} is not an email campaign",
            }
        
        with session_scope() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {
                    "success": False,
                    "error": f"User {user_id} not found",
                }
            
            service = MarketingCampaignService(db)
            # Use send_campaign with a limit of 1, filtering for this user
            # Or implement a direct single-user email method
            result = service._send_email_campaign(
                campaign_type=campaign_enum,
                candidates=[user],
                dry_run=False,
            )
        
        return {
            "success": result.get("sent", 0) > 0,
            "task_id": self.request.id,
            **result,
        }
    except Exception as e:
        logger.exception("[CAMPAIGN_TASK] Single email failed for user %d: %s", user_id, e)
        return {
            "success": False,
            "error": str(e),
            "task_id": self.request.id,
        }
