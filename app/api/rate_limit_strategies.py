"""Dynamic rate limiting strategies based on subscription plans.

Follows SOLID principles:
- Single Responsibility: Each strategy class handles one plan's rate limits
- Open/Closed: Extensible via Strategy pattern, closed for modification
- Liskov Substitution: All strategies implement RateLimitStrategy protocol
- Interface Segregation: Minimal protocol interface (get_limit method)
- Dependency Inversion: rate_limit.py depends on protocol, not concrete strategies

Rate limits by plan:
- FREE: 10 requests/minute (strict limits to prevent abuse)
- STARTER: 30 requests/minute
- PRO: 60 requests/minute  
- BUSINESS: 100 requests/minute
"""

from __future__ import annotations

from typing import Protocol


class RateLimitStrategy(Protocol):
    """Protocol defining rate limit strategy interface (Strategy Pattern)."""
    
    def get_limit(self) -> str:
        """Return rate limit string in format '10/minute' or '100/hour'."""
        ...
    
    def get_requests_per_minute(self) -> int:
        """Return numeric limit for programmatic access."""
        ...


class FreeplanRateLimitStrategy:
    """Rate limit strategy for FREE tier users.
    
    Conservative limits to prevent abuse while allowing basic usage.
    """
    
    def get_limit(self) -> str:
        return "10/minute"
    
    def get_requests_per_minute(self) -> int:
        return 10


class StarterPlanRateLimitStrategy:
    """Rate limit strategy for STARTER tier users.
    
    Moderate limits for small businesses getting started.
    """
    
    def get_limit(self) -> str:
        return "30/minute"
    
    def get_requests_per_minute(self) -> int:
        return 30


class ProPlanRateLimitStrategy:
    """Rate limit strategy for PRO tier users.
    
    Higher limits for active businesses with regular usage.
    """
    
    def get_limit(self) -> str:
        return "60/minute"
    
    def get_requests_per_minute(self) -> int:
        return 60


class BusinessPlanRateLimitStrategy:
    """Rate limit strategy for BUSINESS tier users.
    
    High limits for established businesses with heavy usage.
    """
    
    def get_limit(self) -> str:
        return "100/minute"
    
    def get_requests_per_minute(self) -> int:
        return 100


def get_rate_limit_strategy(plan: str) -> RateLimitStrategy:
    """Factory function to get rate limit strategy for a subscription plan.
    
    Follows Factory pattern and Open/Closed Principle:
    - Open for extension: Add new plan strategies by extending this function
    - Closed for modification: Existing strategies don't change
    
    Args:
        plan: Subscription plan name (free, starter, pro, business)
        
    Returns:
        RateLimitStrategy implementation for the plan
        
    Example:
        >>> strategy = get_rate_limit_strategy("pro")
        >>> strategy.get_limit()
        '60/minute'
    """
    strategies: dict[str, type[RateLimitStrategy]] = {
        "free": FreeplanRateLimitStrategy,
        "starter": StarterPlanRateLimitStrategy,
        "pro": ProPlanRateLimitStrategy,
        "business": BusinessPlanRateLimitStrategy,
    }
    
    strategy_class = strategies.get(plan.lower(), FreeplanRateLimitStrategy)
    return strategy_class()


def get_plan_from_token(token: str | None) -> str:
    """Extract user's subscription plan from JWT access token.
    
    Args:
        token: JWT access token (Bearer token without 'Bearer ' prefix)
        
    Returns:
        Plan name (lowercase) or 'free' if token invalid/missing
    """
    if not token:
        return "free"
    
    try:
        from app.core.security import decode_token, TokenType
        payload = decode_token(token, expected_type=TokenType.ACCESS)
        return payload.get("plan", "free").lower()
    except Exception:
        # If token invalid, treat as free tier for rate limiting
        return "free"
