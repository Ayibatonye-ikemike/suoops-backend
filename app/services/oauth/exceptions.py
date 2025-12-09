"""OAuth service exceptions."""


class OAuthProviderError(Exception):
    """Raised when OAuth provider communication fails."""


class OAuthTokenError(OAuthProviderError):
    """Raised when token exchange fails."""


class OAuthUserInfoError(OAuthProviderError):
    """Raised when fetching user info fails."""
