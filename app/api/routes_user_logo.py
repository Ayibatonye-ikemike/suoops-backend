"""Logo upload/delete endpoints split from routes_user.py."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import AdminUserDep
from app.api.rate_limit import limiter
from app.db.session import get_db
from app.models import models, schemas
from app.storage.s3_client import s3_client
from app.utils.feature_gate import require_plan_feature
from app.utils.file_validation import get_safe_extension, validate_file_magic_bytes

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])


@router.post("/me/logo", response_model=schemas.MessageOut)
@limiter.limit("5/minute")
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    current_user_id: AdminUserDep = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Upload custom logo (Pro+ feature)."""
    try:
        # Check if user has Pro or Business plan
        require_plan_feature(db, current_user_id, "custom_branding", "Custom Logo Branding")
        
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image (PNG, JPG, JPEG, or SVG)")
        allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Unsupported image type. Allowed: PNG, JPG, JPEG, SVG")
        content = await file.read()
        max_size = 5 * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")
        
        # Validate magic bytes match claimed content type (prevents spoofed Content-Type)
        if not validate_file_magic_bytes(content, file.content_type):
            raise HTTPException(
                status_code=400,
                detail="File content does not match its declared type. Upload a valid image file."
            )
        
        user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        ext = get_safe_extension(file.filename, file.content_type)
        key = f"logos/user_{current_user_id}.{ext}"
        logger.info("Uploading logo for user %s: %s bytes, type: %s", current_user_id, len(content), file.content_type)
        logo_url = await s3_client.upload_file(content, key, content_type=file.content_type)
        user.logo_url = logo_url
        db.commit()
        logger.info("Logo uploaded successfully for user %s: %s", current_user_id, logo_url)
        return schemas.MessageOut(detail="Logo uploaded successfully")
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        logger.error("Failed to upload logo for user %s: %s", current_user_id, str(e), exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to upload logo. Please try again.")


@router.delete("/me/logo", response_model=schemas.MessageOut)
def delete_logo(
    current_user_id: AdminUserDep,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.query(models.User).filter(models.User.id == current_user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.logo_url:
        raise HTTPException(status_code=404, detail="No logo configured")
    user.logo_url = None
    db.commit()
    return schemas.MessageOut(detail="Logo removed successfully")
