"""OAuth 2.0 / OpenID Connect Service Module.

Professional SSO implementation supporting multiple OAuth providers
with a clean abstraction layer.

Follows SRP: Each class has one responsibility.
Follows DRY: Reusable OAuth flow for any provider.
Follows OOP: Provider pattern with polymorphism.

Providers:
- Google (OAuth 2.0 + OpenID Connect)
- Microsoft (planned)
- Apple (planned)
"""
from .exceptions import (
    OAuthProviderError,
    OAuthTokenError,
    OAuthUserInfoError,
)
from .providers import (
    OAuthProvider,
    GoogleOAuthProvider,
)
from .service import OAuthService
from .factory import create_oauth_service

__all__ = [
    # Exceptions
    "OAuthProviderError",
    "OAuthTokenError",
    "OAuthUserInfoError",
    # Providers
    "OAuthProvider",
    "GoogleOAuthProvider",
    # Service
    "OAuthService",
    # Factory
    "create_oauth_service",
]
