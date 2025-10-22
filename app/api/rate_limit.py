from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

storage_uri = "memory://"
if settings.ENV.lower() == "prod":
    # Add SSL parameters for Heroku Redis
    redis_url = settings.REDIS_URL
    if redis_url and redis_url.startswith("rediss://"):
        storage_uri = f"{redis_url}?ssl_cert_reqs=none"
    else:
        storage_uri = redis_url or "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)
