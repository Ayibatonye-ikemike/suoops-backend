from fastapi import APIRouter, Depends
from app.core.cache import cached
from app.core.rbac import admin_required
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import models
from app.core.audit import log_audit_event

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users/count")
async def user_count(db: Session = Depends(get_db), admin_user=Depends(admin_required)) -> dict:
    import time

    async def _produce():
        total = db.query(models.User).count()
        result = {"total_users": total, "ts": int(time.time())}
        # Audit only when freshly produced (cache miss)
        log_audit_event("admin.users.count", user_id=admin_user.id, total_users=total)
        return result  # type: ignore

    return await cached("admin:total_users", 30, _produce)
