"""
Centralized Redis client manager with connection pooling.
Prevents connection limit issues by reusing a single connection pool.
"""
import logging
import ssl
import certifi
import redis
from redis.connection import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_client: redis.Redis | None = None


def get_redis_pool() -> ConnectionPool:
    """Get or create a shared Redis connection pool."""
    global _pool
    if _pool is not None:
        return _pool
    
    redis_url = settings.REDIS_URL
    
    # Parse connection parameters
    pool_kwargs = {
        "max_connections": 10,  # Conservative limit for Heroku's 20 connection max
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
        "retry_on_timeout": True,
        "health_check_interval": 30,
    }
    
    # Handle SSL for rediss:// URLs
    if redis_url.startswith("rediss://"):
        ssl_cert_reqs_str = settings.REDIS_SSL_CERT_REQS or "none"
        
        # Map string to ssl constant
        if ssl_cert_reqs_str.lower() == "required":
            cert_reqs = ssl.CERT_REQUIRED
        elif ssl_cert_reqs_str.lower() == "optional":
            cert_reqs = ssl.CERT_OPTIONAL
        else:
            cert_reqs = ssl.CERT_NONE
        
        ca_certs = settings.REDIS_SSL_CA_CERTS or certifi.where()
        
        pool_kwargs["connection_class"] = redis.connection.SSLConnection
        pool_kwargs["ssl_cert_reqs"] = cert_reqs
        pool_kwargs["ssl_ca_certs"] = ca_certs
        
        logger.info(
            "Creating Redis SSL pool with cert_reqs=%s, ca_certs=%s",
            ssl_cert_reqs_str,
            ca_certs,
        )
    
    _pool = ConnectionPool.from_url(redis_url, **pool_kwargs)
    logger.info("Redis connection pool created (max_connections=10)")
    return _pool


def get_redis_client() -> redis.Redis:
    """Get or create a Redis client using the shared connection pool."""
    global _client
    if _client is not None:
        return _client
    
    pool = get_redis_pool()
    _client = redis.Redis(connection_pool=pool)
    
    # Test connection
    try:
        _client.ping()
        logger.info("Redis client connected successfully")
    except Exception as e:
        logger.error("Redis connection failed: %s", e)
        raise
    
    return _client


def close_redis_pool():
    """Close the Redis connection pool. Called on app shutdown."""
    global _pool, _client
    if _client is not None:
        _client.close()
        _client = None
    if _pool is not None:
        _pool.disconnect()
        _pool = None
    logger.info("Redis pool closed")
