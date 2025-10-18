from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

storage_uri = "memory://"
if settings.ENV.lower() == "prod":
    storage_uri = settings.REDIS_URL

limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)
