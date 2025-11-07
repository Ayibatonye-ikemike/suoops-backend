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

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=data, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Token exchange failed: {e.response.text}")
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
        return ["openid", "email", "profile"]

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
            # Update last login
            user.updated_at = datetime.now(timezone.utc)
            logger.info(f"Existing user logged in via {oauth_provider}: {email}")
        else:
            # Create new user
            user = User(
                email=email,
                business_name=name or email.split("@")[0],
                # OAuth users don't have passwords - they always use SSO
                password_hash="",  # Empty for OAuth-only accounts
                phone_number=None,
            )
            self.db.add(user)
            logger.info(f"New user created via {oauth_provider}: {email}")

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
