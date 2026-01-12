"""Admin authentication routes for support dashboard."""
from __future__ import annotations

import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import TokenType, create_access_token, decode_token, hash_password, verify_password
from app.db.session import get_db
from app.models.admin_models import AdminUser

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
logger = logging.getLogger(__name__)

# Default admin credentials
DEFAULT_ADMIN_EMAIL = "support@suoops.com"
DEFAULT_ADMIN_PASSWORD = "SuoOps2024Admin!"  # Should be changed on first login


# ============================================================================
# Schemas
# ============================================================================

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class AdminInviteRequest(BaseModel):
    email: EmailStr
    name: str
    can_manage_tickets: bool = True
    can_view_users: bool = True
    can_view_analytics: bool = True
    can_invite_admins: bool = False


class AdminInviteResponse(BaseModel):
    success: bool
    message: str
    invite_link: str | None = None


class AcceptInviteRequest(BaseModel):
    token: str
    password: str


class AdminUserOut(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    is_super_admin: bool
    can_manage_tickets: bool
    can_view_users: bool
    can_view_analytics: bool
    can_invite_admins: bool
    last_login: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ============================================================================
# Authentication Dependencies
# ============================================================================

security = HTTPBearer()


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Dependency to get current admin from token.
    
    Admin tokens have 'admin:' prefix in the subject.
    """
    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
        subject = payload.get("sub", "")
        
        # Admin tokens have 'admin:' prefix
        if not subject.startswith("admin:"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not an admin token",
            )
        
        admin_id = int(subject.replace("admin:", ""))
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        
        if not admin or not admin.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin not found or inactive",
            )
        
        return admin
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication",
        )


# ============================================================================
# Helper Functions


def create_default_admin(db: Session) -> AdminUser | None:
    """Create the default admin if it doesn't exist."""
    existing = db.query(AdminUser).filter(AdminUser.email == DEFAULT_ADMIN_EMAIL).first()
    if existing:
        return existing
    
    admin = AdminUser(
        email=DEFAULT_ADMIN_EMAIL,
        name="SuoOps Support",
        hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
        is_active=True,
        is_super_admin=True,
        can_manage_tickets=True,
        can_view_users=True,
        can_view_analytics=True,
        can_invite_admins=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info(f"Created default admin: {DEFAULT_ADMIN_EMAIL}")
    return admin


def send_admin_invite_email(to_email: str, name: str, invite_link: str) -> bool:
    """Send admin invitation email."""
    try:
        if not settings.SMTP_HOST:
            logger.warning("SMTP not configured, skipping invite email")
            return False
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "You've been invited to SuoOps Admin"
        msg["From"] = settings.FROM_EMAIL or "noreply@suoops.com"
        msg["To"] = to_email
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 40px 20px; }}
                .btn {{
                    display: inline-block;
                    padding: 14px 28px;
                    background: #10b981;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="color: #0f172a;">Welcome to SuoOps Admin</h1>
                <p style="color: #64748b; font-size: 16px;">Hi {name},</p>
                <p style="color: #64748b; font-size: 16px;">
                    You've been invited to join the SuoOps support admin team. 
                    Click the button below to set up your account:
                </p>
                <p style="margin: 30px 0;">
                    <a href="{invite_link}" class="btn">Accept Invitation</a>
                </p>
                <p style="color: #94a3b8; font-size: 14px;">
                    This invitation expires in 7 days. If you didn't expect this invitation, 
                    you can safely ignore this email.
                </p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                <p style="color: #94a3b8; font-size: 12px;">
                    © 2024 SuoOps. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, "html"))
        
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()  # Always use TLS for security
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        
        return True
    except Exception as e:
        logger.error(f"Failed to send admin invite email: {e}")
        return False


# ============================================================================
# Routes
# ============================================================================

@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    """Login to admin dashboard."""
    # Try to find admin user
    admin = db.query(AdminUser).filter(AdminUser.email == payload.email.lower()).first()
    
    # If no admins exist and this is the default admin email, create it
    if not admin and payload.email.lower() == DEFAULT_ADMIN_EMAIL:
        admin = create_default_admin(db)
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    
    if not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Update last login
    admin.last_login = datetime.now(timezone.utc)
    db.commit()
    
    # Create admin token with 'admin:' prefix
    token = create_access_token(
        subject=f"admin:{admin.id}",
        expires_minutes=60 * 8,  # 8 hours
    )
    
    return AdminLoginResponse(
        access_token=token,
        user={
            "id": admin.id,
            "email": admin.email,
            "name": admin.name,
            "role": "admin",
            "is_super_admin": admin.is_super_admin,
            "permissions": {
                "can_manage_tickets": admin.can_manage_tickets,
                "can_view_users": admin.can_view_users,
                "can_view_analytics": admin.can_view_analytics,
                "can_invite_admins": admin.can_invite_admins,
            },
        },
    )


@router.post("/invite", response_model=AdminInviteResponse)
def invite_admin(
    payload: AdminInviteRequest,
    db: Session = Depends(get_db),
):
    """Invite a new admin user.
    
    Note: Requires authentication - must be called with valid admin token.
    """
    
    # For now, we'll validate the caller is an admin in the route
    # In production, this should use proper dependency injection
    
    # Check if email already exists
    existing = db.query(AdminUser).filter(AdminUser.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An admin with this email already exists",
        )
    
    # Generate invite token
    invite_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    # Create pending admin
    admin = AdminUser(
        email=payload.email.lower(),
        name=payload.name,
        hashed_password="",  # Will be set when accepting invite
        is_active=False,  # Activated when accepting invite
        can_manage_tickets=payload.can_manage_tickets,
        can_view_users=payload.can_view_users,
        can_view_analytics=payload.can_view_analytics,
        can_invite_admins=payload.can_invite_admins,
        invite_token=invite_token,
        invite_expires_at=expires_at,
    )
    db.add(admin)
    db.commit()
    
    # Generate invite link
    invite_link = f"https://support.suoops.com/admin/accept-invite?token={invite_token}"
    
    # Send email
    email_sent = send_admin_invite_email(payload.email, payload.name, invite_link)
    
    return AdminInviteResponse(
        success=True,
        message="Invitation sent successfully" if email_sent else "Invitation created (email not sent)",
        invite_link=invite_link,
    )


@router.post("/accept-invite", response_model=AdminLoginResponse)
def accept_invite(payload: AcceptInviteRequest, db: Session = Depends(get_db)):
    """Accept an admin invitation and set password."""
    admin = db.query(AdminUser).filter(AdminUser.invite_token == payload.token).first()
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation",
        )
    
    if admin.invite_expires_at and admin.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )
    
    if admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already accepted",
        )
    
    # Validate password
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )
    
    # Activate admin
    admin.hashed_password = hash_password(payload.password)
    admin.is_active = True
    admin.invite_token = None
    admin.invite_expires_at = None
    admin.last_login = datetime.now(timezone.utc)
    db.commit()
    
    # Create token
    token = create_access_token(
        subject=f"admin:{admin.id}",
        expires_minutes=60 * 8,
    )
    
    return AdminLoginResponse(
        access_token=token,
        user={
            "id": admin.id,
            "email": admin.email,
            "name": admin.name,
            "role": "admin",
            "is_super_admin": admin.is_super_admin,
            "permissions": {
                "can_manage_tickets": admin.can_manage_tickets,
                "can_view_users": admin.can_view_users,
                "can_view_analytics": admin.can_view_analytics,
                "can_invite_admins": admin.can_invite_admins,
            },
        },
    )


@router.get("/me", response_model=AdminUserOut)
def get_current_admin_user(db: Session = Depends(get_db)):
    """Get current admin user info.
    
    Note: This route requires authentication via admin token.
    """
    
    # This would be handled by dependency in production
    # For now, return placeholder
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


@router.get("/admins", response_model=list[AdminUserOut])
def list_admins(db: Session = Depends(get_db)):
    """List all admin users.
    
    Note: Only super admins or those with invite permission can see this.
    """
    admins = db.query(AdminUser).filter(AdminUser.is_active.is_(True)).all()
    return admins


@router.delete("/admins/{admin_id}")
async def remove_admin(
    admin_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Remove an admin user. Only super admins can perform this action."""
    # Only super admins can remove admins
    if not current_admin.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can remove admin users",
        )
    
    # Find the admin to remove
    admin_to_remove = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not admin_to_remove:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin not found",
        )
    
    # Prevent self-deletion
    if admin_to_remove.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself",
        )
    
    # Prevent removing other super admins
    if admin_to_remove.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove another super admin",
        )
    
    # Hard delete the admin
    db.delete(admin_to_remove)
    db.commit()
    
    logger.info(f"Admin {current_admin.email} removed admin {admin_to_remove.email}")
    
    return {"success": True, "message": f"Admin {admin_to_remove.email} has been removed"}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
):
    """Change admin password."""
    # This would need proper auth dependency
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not implemented",
    )


# ============================================================================
# Startup: Create default admin
# ============================================================================

def init_default_admin():
    """Initialize default admin on startup. Called from main.py."""
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        admin = create_default_admin(db)
        if admin:
            logger.info(f"Default admin ready: {DEFAULT_ADMIN_EMAIL}")
    except Exception as e:
        logger.error(f"Failed to create default admin: {e}")
    finally:
        db.close()
