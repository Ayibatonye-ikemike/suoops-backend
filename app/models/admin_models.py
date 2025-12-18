"""Admin user models for support dashboard."""
from __future__ import annotations

import datetime as dt
from sqlalchemy import String, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class AdminUser(Base):
    """Admin users for support.suoops.com dashboard.
    
    Separate from regular User model to allow password-based auth
    for admin access while keeping OTP-only for regular users.
    """
    __tablename__ = "admin_users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Permissions
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    
    # Permissions for different sections
    can_manage_tickets: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    can_view_users: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    can_view_analytics: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    can_invite_admins: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    
    # Tracking
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
    )
    
    # Who invited this admin (NULL for system-created default admin)
    invited_by_id: Mapped[int | None] = mapped_column(nullable=True)
    
    # Invite token (for pending invitations)
    invite_token: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    invite_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self) -> str:
        return f"<AdminUser {self.email}>"
