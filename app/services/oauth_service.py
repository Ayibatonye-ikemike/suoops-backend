"""
OAuth 2.0 / OpenID Connect Service - Professional SSO Implementation.

Supports multiple OAuth providers with a clean abstraction layer.
Follows SRP: Each class has one responsibility.
Follows DRY: Reusable OAuth flow for any provider.
Follows OOP: Provider pattern with polymorphism.

Providers:
- Google (OAuth 2.0 + OpenID Connect)
- Microsoft (planned)
- Apple (planned)
"""

import datetime as dt
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.models import User
from app.models.oauth_models import OAuthToken
from app.utils.token_encryption import encrypt_token

logger = logging.getLogger(__name__)


class OAuthProviderError(Exception):
    """Raised when OAuth provider communication fails."""


class OAuthTokenError(OAuthProviderError):
    """Raised when token exchange fails."""


class OAuthUserInfoError(OAuthProviderError):
    """Raised when fetching user info fails."""


class OAuthProvider(ABC):
    """
    Abstract base class for OAuth 2.0 providers.
    
    Implements the OAuth 2.0 authorization code flow.
    Subclasses must implement provider-specific details.
    """

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """
        Initialize OAuth provider.
        
        Args:
            client_id: OAuth client ID from provider
            client_secret: OAuth client secret from provider
            redirect_uri: Callback URL for OAuth flow
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @property
    @abstractmethod
    def authorization_url(self) -> str:
        """Provider's authorization endpoint."""
        pass

    @property
    @abstractmethod
    def token_url(self) -> str:
        """Provider's token exchange endpoint."""
        pass

    @property
    @abstractmethod
    def user_info_url(self) -> str:
        """Provider's user info endpoint."""
        pass

    @property
    @abstractmethod
    def scopes(self) -> list[str]:
        """Required OAuth scopes."""
        pass

    def get_authorization_url(self, state: str) -> str:
        """
        Generate authorization URL for OAuth flow.
        
        Args:
            state: CSRF protection token
            
        Returns:
            Full authorization URL with query parameters
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }
        
        return f"{self.authorization_url}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from OAuth callback
            
        Returns:
            Token response with access_token, refresh_token, etc.
            
        Raises:
            OAuthTokenError: If token exchange fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        
        # Log sanitized exchange metadata (no secrets)
        code_hash = abs(hash(code))
        logger.info(
            f"Token exchange attempt | "
            f"provider=google "
            f"code_hash={code_hash} "
            f"client_id_prefix={self.client_id[:20]}..."
        )

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=data, timeout=10.0)
                response.raise_for_status()
                logger.info(f"Token exchange SUCCESS | code_hash={hash(code)}")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Token exchange failed | "
                    f"code_hash={hash(code)} "
                    f"status={e.response.status_code} "
                    f"response={e.response.text}"
                )
                raise OAuthTokenError(f"Token exchange failed: {e.response.status_code}") from e
            except httpx.RequestError as e:
                logger.error(f"Token exchange request failed: {str(e)}")
                raise OAuthTokenError("Failed to connect to OAuth provider") from e

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """
        Fetch user information using access token.
        
        Args:
            access_token: OAuth access token
            
        Returns:
            User profile information
            
        Raises:
            OAuthUserInfoError: If fetching user info fails
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.user_info_url, headers=headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"User info fetch failed: {e.response.text}")
                raise OAuthUserInfoError(f"User info fetch failed: {e.response.status_code}") from e
            except httpx.RequestError as e:
                logger.error(f"User info request failed: {str(e)}")
                raise OAuthUserInfoError("Failed to connect to OAuth provider") from e

    @abstractmethod
    def extract_user_data(self, user_info: dict[str, Any]) -> dict[str, str]:
        """
        Extract standardized user data from provider response.
        
        Args:
            user_info: Raw user info from provider
            
        Returns:
            Standardized user data with keys: email, name, picture
        """
        pass


class GoogleOAuthProvider(OAuthProvider):
    """Google OAuth 2.0 / OpenID Connect implementation."""

    @property
    def authorization_url(self) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth"

    @property
    def token_url(self) -> str:
        return "https://oauth2.googleapis.com/token"

    @property
    def user_info_url(self) -> str:
        return "https://www.googleapis.com/oauth2/v2/userinfo"

    @property
    def scopes(self) -> list[str]:
        # Minimal scopes for authentication per Google best practices
        # Request additional scopes (e.g., profile) incrementally when needed
        return ["openid", "email"]

    def extract_user_data(self, user_info: dict[str, Any]) -> dict[str, str]:
        """
        Extract user data from Google user info response.
        
        Expected fields:
        - email: User's email address
        - name: Full name
        - picture: Profile picture URL
        - verified_email: Email verification status
        """
        return {
            "email": user_info.get("email", ""),
            "name": user_info.get("name", ""),
            "picture": user_info.get("picture", ""),
            "email_verified": user_info.get("verified_email", False),
        }


class OAuthService:
    """
    OAuth service for managing SSO authentication.
    
    Responsibilities:
    - Coordinate OAuth flow
    - Provision users from OAuth data
    - Generate JWT tokens for authenticated users
    
    Follows SRP: Only handles OAuth-related business logic.
    """

    def __init__(self, db: Session):
        """
        Initialize OAuth service.
        
        Args:
            db: Database session for user operations
        """
        self.db = db
        self._providers: dict[str, OAuthProvider] = {}

    def register_provider(self, name: str, provider: OAuthProvider) -> None:
        """
        Register an OAuth provider.
        
        Args:
            name: Provider identifier (e.g., "google")
            provider: OAuthProvider instance
        """
        self._providers[name] = provider
        logger.info(f"Registered OAuth provider: {name}")

    def get_provider(self, name: str) -> OAuthProvider:
        """
        Get registered OAuth provider.
        
        Args:
            name: Provider identifier
            
        Returns:
            OAuthProvider instance
            
        Raises:
            ValueError: If provider not registered
        """
        if name not in self._providers:
            raise ValueError(f"OAuth provider '{name}' not registered")
        return self._providers[name]

    def _store_oauth_tokens(
        self,
        user_id: int,
        provider: str,
        access_token: str,
        refresh_token: str,
        token_response: dict[str, Any],
    ) -> None:
        """
        Store or update encrypted OAuth tokens for user.
        
        Args:
            user_id: User ID
            provider: OAuth provider name
            access_token: OAuth access token to encrypt
            refresh_token: OAuth refresh token to encrypt
            token_response: Full token response with metadata
        """
        # Calculate token expiration if provided
        expires_at = None
        if "expires_in" in token_response:
            expires_in = token_response["expires_in"]
            expires_at = datetime.now(timezone.utc) + dt.timedelta(seconds=expires_in)
        
        # Extract scopes if provided
        scopes = None
        if "scope" in token_response:
            scopes = token_response["scope"].split() if isinstance(token_response["scope"], str) else token_response["scope"]
        
        # Check if token already exists for this user+provider
        existing_token = self.db.query(OAuthToken).filter(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == provider,
        ).first()
        
        if existing_token:
            # Update existing token
            existing_token.access_token_encrypted = encrypt_token(access_token)
            existing_token.refresh_token_encrypted = encrypt_token(refresh_token)
            existing_token.token_type = token_response.get("token_type", "bearer")
            existing_token.expires_at = expires_at
            existing_token.scopes = scopes
            existing_token.updated_at = datetime.now(timezone.utc)
            existing_token.revoked_at = None  # Clear revocation if re-authenticating
            logger.info(f"Updated OAuth tokens for user {user_id} provider {provider}")
        else:
            # Create new token entry
            new_token = OAuthToken(
                user_id=user_id,
                provider=provider,
                access_token_encrypted=encrypt_token(access_token),
                refresh_token_encrypted=encrypt_token(refresh_token),
                token_type=token_response.get("token_type", "bearer"),
                expires_at=expires_at,
                scopes=scopes,
            )
            self.db.add(new_token)
            logger.info(f"Created OAuth tokens for user {user_id} provider {provider}")
        
        self.db.commit()

    def _get_or_create_user(self, email: str, name: str, oauth_provider: str) -> User:
        """
        Get existing user or create new one from OAuth data.
        
        Args:
            email: User email from OAuth provider
            name: User full name
            oauth_provider: Provider name (e.g., "google")
            
        Returns:
            User instance (existing or newly created)
        """
        # Check if user exists
        user = self.db.query(User).filter(User.email == email).first()

        if user:
            # Update last_login timestamp
            user.last_login = datetime.now(timezone.utc)
            logger.info(f"Existing user logged in via {oauth_provider}: {email}")
        else:
            # Fallback phone requirement: model requires 'phone' (unique, non-null). Derive synthetic phone.
            synthetic_phone = f"oauth_{oauth_provider}_{email.split('@')[0]}"
            # Ensure length constraint (32) and uniqueness attempt (append timestamp fragment if needed)
            if len(synthetic_phone) > 30:
                synthetic_phone = synthetic_phone[:30]
            attempt = 0
            base_phone = synthetic_phone
            while self.db.query(User).filter(User.phone == synthetic_phone).first():
                attempt += 1
                synthetic_phone = f"{base_phone[:28]}{attempt:02d}"  # keep within 32 chars

            user = User(
                phone=synthetic_phone,
                email=email,
                name=name or email.split("@")[0],
                business_name=name or email.split("@")[0],
            )
            self.db.add(user)
            logger.info(f"New user created via {oauth_provider}: {email} (phone={synthetic_phone})")

        self.db.commit()
        self.db.refresh(user)
        return user

    async def authenticate_with_code(
        self, provider_name: str, code: str
    ) -> dict[str, str]:
        """
        Authenticate user with OAuth authorization code.
        
        Complete OAuth flow:
        1. Exchange code for access token
        2. Fetch user info from provider
        3. Provision user in database
        4. Generate JWT tokens
        
        Args:
            provider_name: OAuth provider identifier
            code: Authorization code from OAuth callback
            
        Returns:
            JWT tokens: access_token, refresh_token, token_type
            
        Raises:
            OAuthProviderError: If OAuth flow fails
        """
        provider = self.get_provider(provider_name)

        # Exchange code for tokens
        token_response = await provider.exchange_code_for_token(code)
        access_token = token_response.get("access_token")

        if not access_token:
            raise OAuthTokenError("No access token in response")

        # Fetch user information
        user_info = await provider.get_user_info(access_token)
        user_data = provider.extract_user_data(user_info)

        # Validate required fields
        if not user_data.get("email"):
            raise OAuthUserInfoError("Email not provided by OAuth provider")

        # Provision user
        user = self._get_or_create_user(
            email=user_data["email"],
            name=user_data.get("name", ""),
            oauth_provider=provider_name,
        )

        # Store OAuth tokens securely (encrypted at rest)
        oauth_refresh_token = token_response.get("refresh_token")
        if oauth_refresh_token:
            self._store_oauth_tokens(
                user_id=user.id,
                provider=provider_name,
                access_token=access_token,
                refresh_token=oauth_refresh_token,
                token_response=token_response,
            )
            logger.info(f"Stored encrypted OAuth tokens for {provider_name}: {user.email}")
        else:
            logger.warning(f"No refresh token from {provider_name} for {user.email}")

        # Generate JWT tokens
        access_token_jwt = create_access_token(str(user.id))
        refresh_token_jwt = create_refresh_token(str(user.id))

        logger.info(f"User authenticated via {provider_name}: {user.email}")

        return {
            "access_token": access_token_jwt,
            "refresh_token": refresh_token_jwt,
            "token_type": "bearer",
        }


def create_oauth_service(db: Session) -> OAuthService:
    """
    Factory function to create configured OAuth service.
    
    Automatically registers all enabled OAuth providers.
    
    Args:
        db: Database session
        
    Returns:
        Configured OAuthService instance
    """
    service = OAuthService(db)

    # Register Google OAuth if configured
    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        google_provider = GoogleOAuthProvider(
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            redirect_uri=f"{settings.BACKEND_URL}/auth/oauth/google/callback",
        )
        service.register_provider("google", google_provider)
        logger.info("Google OAuth provider enabled")
    else:
        logger.warning("Google OAuth not configured (missing client ID/secret)")

    return service
