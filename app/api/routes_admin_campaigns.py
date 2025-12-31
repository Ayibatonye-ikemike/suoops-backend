"""Admin API for Marketing Campaigns.

Provides endpoints to:
- Preview campaign candidates (dry run)
- Send marketing campaigns
- Send to individual users

Note: These endpoints require admin authentication (support admin).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes_admin_auth import get_current_admin, AdminUser
from app.db.session import get_db
from app.models import models
from app.services.marketing_campaigns import (
    CampaignType,
    MarketingCampaignService,
    CAMPAIGN_TEMPLATES,
    EMAIL_CAMPAIGNS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/campaigns", tags=["Admin - Marketing Campaigns"])


class CampaignRequest(BaseModel):
    """Request to send a marketing campaign."""
    campaign_type: CampaignType
    dry_run: bool = True  # Default to dry run for safety
    limit: int = 50


class SingleUserCampaignRequest(BaseModel):
    """Request to send campaign to a single user."""
    phone: str
    campaign_type: CampaignType
    user_name: str = "there"
    remaining_invoices: int | None = None  # For low_balance_reminder
    invoice_count: int | None = None  # For pro_upgrade


class CampaignResponse(BaseModel):
    """Response from campaign execution."""
    campaign: str
    template: str
    dry_run: bool
    candidates: int
    sent: int
    failed: int
    skipped: int
    details: list[dict]


class CampaignListResponse(BaseModel):
    """List of available campaigns."""
    campaigns: list[dict]


@router.get("/", response_model=CampaignListResponse)
async def list_campaigns(
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
) -> CampaignListResponse:
    """List all available marketing campaigns."""
    campaigns = [
        {
            "type": campaign_type.value,
            "template": config["template_name"],
            "description": config["description"],
            "parameters": config["params"],
            "goal": config.get("goal", "Engage users"),
            "channel": config.get("channel", "whatsapp"),  # Default to whatsapp
        }
        for campaign_type, config in CAMPAIGN_TEMPLATES.items()
    ]
    return CampaignListResponse(campaigns=campaigns)


@router.post("/preview")
async def preview_campaign(
    request: CampaignRequest,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
) -> dict:
    """Preview campaign candidates without sending (always dry run)."""
    try:
        service = MarketingCampaignService(db)
        
        # Force dry run for preview
        result = service.send_campaign(
            campaign_type=request.campaign_type,
            dry_run=True,
            limit=request.limit,
        )
        
        return {
            "success": True,
            **result,
        }
    except Exception as e:
        logger.exception("[CAMPAIGN] Preview failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to preview campaign: {str(e)}"
        )


@router.post("/send")
async def send_campaign(
    request: CampaignRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(get_current_admin)],
) -> dict:
    """Send a marketing campaign to eligible users.
    
    WARNING: Set dry_run=False to actually send messages.
    This will send WhatsApp messages to real users!
    """
    try:
        logger.info(
            "[CAMPAIGN] Admin %s initiating %s campaign, dry_run=%s, limit=%d",
            admin.email,
            request.campaign_type.value,
            request.dry_run,
            request.limit,
        )
        
        service = MarketingCampaignService(db)
        
        result = service.send_campaign(
            campaign_type=request.campaign_type,
            dry_run=request.dry_run,
            limit=request.limit,
        )
        
        # Check for errors in result
        if result.get("error"):
            return {
                "success": False,
                **result,
            }
        
        return {
            "success": True,
            **result,
        }
    except Exception as e:
        logger.exception("[CAMPAIGN] Send failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send campaign: {str(e)}"
        )


@router.post("/send-single")
async def send_to_single_user(
    request: SingleUserCampaignRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(get_current_admin)],
) -> dict:
    """Send a marketing template to a single user.
    
    Useful for testing templates before running full campaigns.
    """
    try:
        logger.info(
            "[CAMPAIGN] Admin %s sending %s to %s",
            admin.email,
            request.campaign_type.value,
            request.phone[-4:] if request.phone else "N/A",
        )
        
        service = MarketingCampaignService(db)
        
        extra_params = {}
        if request.remaining_invoices is not None:
            extra_params["remaining_invoices"] = str(request.remaining_invoices)
        if request.invoice_count is not None:
            extra_params["invoice_count"] = str(request.invoice_count)
        
        result = service.send_to_single_user(
            phone=request.phone,
            campaign_type=request.campaign_type,
            user_name=request.user_name,
            extra_params=extra_params if extra_params else None,
        )
        
        # send_to_single_user now returns a dict
        return result
    except Exception as e:
        logger.exception("[CAMPAIGN] Single user send failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send message: {str(e)}"
        )


@router.get("/candidates/{campaign_type}")
async def get_campaign_candidates(
    campaign_type: CampaignType,
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    limit: int = Query(default=20, le=100),
) -> dict:
    """Get list of candidates for a specific campaign type."""
    try:
        service = MarketingCampaignService(db)
        
        if campaign_type == CampaignType.ACTIVATION_WELCOME:
            candidates = service.get_activation_candidates(limit=limit)
            return {
                "success": True,
                "campaign": campaign_type.value,
                "count": len(candidates),
                "candidates": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "phone": u.phone[-4:].rjust(len(u.phone), "*") if u.phone else None,
                        "email": u.email,
                        "signed_up": u.created_at.isoformat() if u.created_at else None,
                    }
                    for u in candidates
                ],
            }
        
        elif campaign_type == CampaignType.WIN_BACK_REMINDER:
            candidates = service.get_winback_candidates(limit=limit)
            return {
                "success": True,
                "campaign": campaign_type.value,
                "count": len(candidates),
                "candidates": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "phone": u.phone[-4:].rjust(len(u.phone), "*") if u.phone else None,
                        "email": u.email,
                    }
                    for u in candidates
                ],
            }
        
        elif campaign_type == CampaignType.LOW_BALANCE_REMINDER:
            candidates = service.get_low_balance_candidates(limit=limit)
            return {
                "success": True,
                "campaign": campaign_type.value,
                "count": len(candidates),
                "candidates": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "phone": u.phone[-4:].rjust(len(u.phone), "*") if u.phone else None,
                        "invoice_balance": balance,
                    }
                    for u, balance in candidates
                ],
            }
        
        elif campaign_type == CampaignType.PRO_UPGRADE:
            candidates = service.get_pro_upgrade_candidates(limit=limit)
            return {
                "success": True,
                "campaign": campaign_type.value,
                "count": len(candidates),
                "candidates": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "phone": u.phone[-4:].rjust(len(u.phone), "*") if u.phone else None,
                        "plan": u.plan.value if u.plan else "free",
                        "invoice_count": count,
                    }
                    for u, count in candidates
                ],
            }
        
        elif campaign_type == CampaignType.INVOICE_PACK_PROMO:
            candidates = service.get_zero_balance_candidates(limit=limit)
            return {
                "success": True,
                "campaign": campaign_type.value,
                "count": len(candidates),
                "candidates": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "phone": u.phone[-4:].rjust(len(u.phone), "*") if u.phone else None,
                        "invoice_balance": u.invoice_balance,
                    }
                    for u in candidates
                ],
            }
        
        elif campaign_type == CampaignType.FIRST_INVOICE_FOLLOWUP:
            candidates = service.get_first_invoice_candidates(limit=limit)
            return {
                "success": True,
                "campaign": campaign_type.value,
                "count": len(candidates),
                "candidates": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "phone": u.phone[-4:].rjust(len(u.phone), "*") if u.phone else None,
                        "signed_up": u.created_at.isoformat() if u.created_at else None,
                    }
                    for u in candidates
                ],
            }
        
        elif campaign_type == CampaignType.EMAIL_WHATSAPP_PROMOTION:
            # Email campaign - show users without verified WhatsApp
            candidates = service.get_whatsapp_unverified_candidates(limit=limit)
            return {
                "success": True,
                "campaign": campaign_type.value,
                "channel": "email",
                "count": len(candidates),
                "candidates": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "email": u.email[:3] + "***" + u.email[u.email.index("@"):] if u.email and "@" in u.email else u.email,
                        "phone": u.phone if u.phone else "Not connected",
                        "phone_verified": u.phone_verified,
                        "signed_up": u.created_at.isoformat() if u.created_at else None,
                    }
                    for u in candidates
                ],
            }
        
        return {"success": True, "campaign": campaign_type.value, "count": 0, "candidates": []}
    except Exception as e:
        logger.exception("[CAMPAIGN] Failed to get candidates: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch candidates: {str(e)}"
        )
