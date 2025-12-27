"""Brevo (Sendinblue) contact sync service.

Handles real-time syncing of users to Brevo contact lists.
"""
import logging
import httpx
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.models import models

logger = logging.getLogger(__name__)

# Brevo list IDs (created via API)
BREVO_LIST_ALL_USERS = 12  # All Users master list


async def sync_user_to_brevo(user: "models.User") -> bool:
    """
    Sync a single user to Brevo "All Users" list.
    
    Called on:
    - User signup (new user)
    - User plan change (update attributes)
    
    Returns True if successful, False otherwise.
    """
    brevo_api_key = getattr(settings, "BREVO_CONTACTS_API_KEY", None)
    if not brevo_api_key:
        logger.debug("BREVO_CONTACTS_API_KEY not configured, skipping sync")
        return False
    
    if not user.email:
        logger.debug("User %s has no email, skipping Brevo sync", user.id)
        return False
    
    contact_data = {
        "email": user.email,
        "attributes": {
            "FIRSTNAME": user.name or "Customer",
            "PHONE": user.phone,
            "PLAN": user.plan.value,
            "INVOICE_BALANCE": getattr(user, 'invoice_balance', 5),
            "BUSINESS_NAME": user.business_name or ""
        },
        "listIds": [BREVO_LIST_ALL_USERS],
        "updateEnabled": True  # Update if contact exists
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.brevo.com/v3/contacts",
                headers={
                    "api-key": brevo_api_key,
                    "Content-Type": "application/json"
                },
                json=contact_data,
                timeout=10.0
            )
            
            if response.status_code in (200, 201, 204):
                logger.info("Synced user %s to Brevo", user.email)
                return True
            elif response.status_code == 400 and "Contact already exist" in response.text:
                # Contact exists, try to update
                return await update_brevo_contact(user)
            else:
                logger.warning(
                    "Brevo sync failed for %s: %s - %s",
                    user.email, response.status_code, response.text
                )
                return False
                
    except Exception as e:
        logger.warning("Brevo sync error for %s: %s", user.email, e)
        return False


async def update_brevo_contact(user: "models.User") -> bool:
    """Update existing contact in Brevo."""
    brevo_api_key = getattr(settings, "BREVO_CONTACTS_API_KEY", None)
    if not brevo_api_key or not user.email:
        return False
    
    update_data = {
        "attributes": {
            "FIRSTNAME": user.name or "Customer",
            "PHONE": user.phone,
            "PLAN": user.plan.value,
            "INVOICE_BALANCE": getattr(user, 'invoice_balance', 5),
            "BUSINESS_NAME": user.business_name or ""
        },
        "listIds": [BREVO_LIST_ALL_USERS]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # URL-encode email for the path
            import urllib.parse
            encoded_email = urllib.parse.quote(user.email, safe='')
            
            response = await client.put(
                f"https://api.brevo.com/v3/contacts/{encoded_email}",
                headers={
                    "api-key": brevo_api_key,
                    "Content-Type": "application/json"
                },
                json=update_data,
                timeout=10.0
            )
            
            if response.status_code in (200, 204):
                logger.info("Updated Brevo contact %s", user.email)
                return True
            else:
                logger.warning(
                    "Brevo update failed for %s: %s",
                    user.email, response.status_code
                )
                return False
                
    except Exception as e:
        logger.warning("Brevo update error for %s: %s", user.email, e)
        return False


def sync_user_to_brevo_sync(user: "models.User") -> bool:
    """
    Synchronous wrapper for sync_user_to_brevo.
    
    Use this in synchronous contexts (like auth_service).
    Runs the async function in a new event loop.
    """
    import asyncio
    
    try:
        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, create a task
            # This won't work directly, so we'll use a different approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    sync_user_to_brevo(user)
                )
                return future.result(timeout=15)
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(sync_user_to_brevo(user))
    except Exception as e:
        logger.warning("Sync wrapper error: %s", e)
        return False
