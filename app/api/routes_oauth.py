"""
OAuth 2.0 / SSO Authentication Routes.

Endpoints:
- GET  /auth/oauth/{provider}/login - Initiate OAuth flow
- GET  /auth/oauth/{provider}/callback - Handle OAuth callback
- GET  /auth/oauth/providers - List available providers

Follows SRP: Only handles HTTP layer for OAuth.
Business logic delegated to OAuthService.
"""

import logging
import secrets
import ssl
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import schemas
from app.services.oauth_service import OAuthProviderError, create_oauth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/oauth", tags=["oauth"])


# Redis client for OAuth state storage (shared across dynos)
_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    """Get or create Redis client for OAuth state storage with SSL support."""
    global _redis_client
    if _redis_client is None:
        # Configure SSL options for Heroku Redis
        ssl_cert_reqs = getattr(settings, "REDIS_SSL_CERT_REQS", "required")
        ssl_options = {}
        
        if ssl_cert_reqs:
            ssl_map = {
                "required": ssl.CERT_REQUIRED,
                "optional": ssl.CERT_OPTIONAL,
                "none": ssl.CERT_NONE,
            }
            chosen = ssl_map.get(str(ssl_cert_reqs).lower())
            if chosen is not None:
                ssl_options["ssl_cert_reqs"] = chosen
        
        if getattr(settings, "REDIS_SSL_CA_CERTS", None):
            ssl_options["ssl_ca_certs"] = settings.REDIS_SSL_CA_CERTS
        
        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            **ssl_options
        )
    return _redis_client


def _generate_state() -> str:
    """
    Generate cryptographically secure state token for CSRF protection.
    
    Returns:
        Random 32-character hex string
    """
    return secrets.token_hex(16)


def _store_oauth_state(state: str, redirect_uri: str) -> None:
    """
    Store OAuth state token in Redis with 10-minute expiration.
    
    Args:
        state: State token for CSRF protection
        redirect_uri: Frontend redirect URI to store with state
    """
    redis_client = _get_redis_client()
    key = f"oauth:state:{state}"
    # Store for 10 minutes (OAuth flow should complete quickly)
    redis_client.setex(key, 600, redirect_uri)
    logger.debug(f"Stored OAuth state: {state}")


def _build_redirect_with_params(base_url: str, params: dict[str, str]) -> str:
    """Append query parameters to an existing URL safely."""
    parsed = urlparse(base_url)
    existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing_params.update(params)
    new_query = urlencode(existing_params)
    return urlunparse(parsed._replace(query=new_query))


def _get_redirect_uri(state: str, consume: bool = True) -> str | None:
    """
    Validate OAuth state token and return redirect URI from Redis.
    
    Args:
        state: State token from OAuth callback
        consume: Whether to delete the state entry after retrieval
        
    Returns:
        Redirect URI if state is valid, None otherwise
    """
    redis_client = _get_redis_client()
    key = f"oauth:state:{state}"
    
    redirect_uri = redis_client.get(key)

    if redirect_uri is None:
        return None

    if consume:
        redis_client.delete(key)
        logger.debug(f"Validated and consumed OAuth state: {state}")
    else:
        logger.debug(f"Validated OAuth state without consuming: {state}")

    return redirect_uri


@router.get("/providers", response_model=schemas.OAuthProvidersOut)
async def list_oauth_providers(db: Annotated[Session, Depends(get_db)]) -> dict:
    """
    List available OAuth providers.
    
    Returns list of configured SSO providers with their capabilities.
    
    Returns:
        {
            "providers": [
                {
                    "name": "google",
                    "display_name": "Google",
                    "enabled": true,
                    "supports_refresh": true
                }
            ]
        }
    """
    oauth_service = create_oauth_service(db)
    providers = []

    # Google provider
    if settings.GOOGLE_CLIENT_ID:
        providers.append({
            "name": "google",
            "display_name": "Google",
            "enabled": True,
            "supports_refresh": True,
            "icon_url": "https://www.google.com/favicon.ico",
        })

    return {"providers": providers}


@router.get("/{provider}/login")
async def oauth_login(
    provider: str,
    redirect_uri: str | None = Query(None, description="Frontend redirect after auth"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Initiate OAuth login flow.
    
    Redirects user to OAuth provider's authorization page.
    
    Args:
        provider: OAuth provider name (e.g., "google")
        redirect_uri: Optional frontend URL to redirect after successful auth
        
    Returns:
        Redirect to OAuth provider's authorization page
        
    Example:
        GET /auth/oauth/google/login?redirect_uri=https://app.suoops.com/dashboard
    """
    try:
        oauth_service = create_oauth_service(db)
        oauth_provider = oauth_service.get_provider(provider)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Generate CSRF protection state and store in Redis
    state = _generate_state()
    _store_oauth_state(state, redirect_uri or settings.FRONTEND_URL)

    # Get authorization URL
    auth_url = oauth_provider.get_authorization_url(state)

    logger.info(f"Initiating OAuth login with {provider}")
    return RedirectResponse(url=auth_url)


@router.get("/{provider}/callback", response_model=schemas.OAuthCallbackOut)
async def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code from OAuth provider"),
    state: str = Query(..., description="CSRF protection token"),
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    Handle OAuth provider callback.
    
    Completes OAuth flow:
    1. Validates CSRF state
    2. Exchanges code for tokens
    3. Fetches user info
    4. Creates/updates user
    5. Returns JWT tokens
    
    Args:
        provider: OAuth provider name
        code: Authorization code from provider
        state: CSRF state token
        
    Returns:
        {
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",
            "token_type": "bearer",
            "redirect_uri": "https://app.suoops.com/dashboard"
        }
        
    Example:
        GET /auth/oauth/google/callback?code=4/xxx&state=abc123
    """
    accept_header = (request.headers.get("accept", "") or "").lower()
    sec_fetch_mode = (request.headers.get("sec-fetch-mode", "") or "").lower()
    expects_json = (
        "application/json" in accept_header
        or (sec_fetch_mode and sec_fetch_mode != "navigate")
    )

    # For browser navigations we redirect back to the frontend with original parameters
    if not expects_json:
        redirect_uri = _get_redirect_uri(state, consume=False)
        if redirect_uri is None:
            logger.warning(f"Invalid OAuth state (non-JSON request): {state}")
            raise HTTPException(
                status_code=400,
                detail="Invalid state token. Possible CSRF attack or expired session.",
            )

        redirect_with_params = _build_redirect_with_params(redirect_uri, {"code": code, "state": state})
        logger.info("Redirecting browser to frontend callback with OAuth code")
        return RedirectResponse(url=redirect_with_params)

    # Validate CSRF state and get redirect URI for token exchange
    redirect_uri = _get_redirect_uri(state, consume=True)
    if redirect_uri is None:
        logger.warning(f"Invalid or consumed OAuth state: {state}")
        raise HTTPException(
            status_code=400,
            detail="Invalid state token. Possible CSRF attack or expired session.",
        )

    try:
        # Authenticate with OAuth code
        oauth_service = create_oauth_service(db)
        tokens = await oauth_service.authenticate_with_code(provider, code)

        logger.info(f"OAuth authentication successful for {provider}")

        return {
            **tokens,
            "redirect_uri": redirect_uri,
        }

    except OAuthProviderError as e:
        logger.error(f"OAuth authentication failed: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"OAuth authentication failed: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error during OAuth callback: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during authentication",
        ) from e


@router.post("/{provider}/revoke")
async def revoke_oauth_access(
    provider: str,
    current_user_id: int,  # Would need proper dependency injection
    db: Session = Depends(get_db),
) -> dict:
    """
    Revoke OAuth access for user.
    
    Removes OAuth provider link from user account.
    User can still login with password if set.
    
    Args:
        provider: OAuth provider to unlink
        current_user_id: Authenticated user ID
        
    Returns:
        {"message": "OAuth access revoked"}
        
    Note: Not fully implemented - requires OAuth token storage
    """
    logger.info(f"OAuth revocation requested for provider {provider}")
    
    # TODO: Implement OAuth token storage and revocation
    # For now, just acknowledge the request
    return {
        "message": f"OAuth {provider} access revocation is pending implementation",
        "status": "not_implemented",
    }
