"""Settings API endpoints (admin-only)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
import logging

from backend.api.auth import require_admin
from backend.models.database import get_db, Setting
from backend.core.config_service import reload_settings_from_db

logger = logging.getLogger("trading_bot")

router = APIRouter(prefix="/api/admin/settings", tags=["settings"])


class SettingResponse(BaseModel):
    """Single setting response."""
    id: int
    key: str
    value: str
    description: Optional[str]
    type: str
    created_at: datetime
    updated_at: datetime
    updated_by_user_id: str


class SettingUpdateRequest(BaseModel):
    """Single setting update in bulk request."""
    key: str
    value: str


@router.get("", response_model=List[SettingResponse])
async def list_settings(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    """
    Get all settings from database.
    
    Returns:
        List of all settings with metadata
    
    Auth:
        Requires admin authentication (401 if not authenticated, 403 if not admin)
    """
    try:
        settings = db.query(Setting).order_by(Setting.key).all()
        return [
            SettingResponse(
                id=s.id,
                key=s.key,
                value=s.value,
                description=s.description,
                type=s.type,
                created_at=s.created_at,
                updated_at=s.updated_at,
                updated_by_user_id=s.updated_by_user_id or "system",
            )
            for s in settings
        ]
    except Exception as e:
        logger.error(f"Failed to list settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve settings")


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    """
    Get a single setting by key.
    
    Args:
        key: Setting key (e.g., "MIROFISH_API_TIMEOUT")
    
    Returns:
        Setting with metadata
    
    Auth:
        Requires admin authentication (401 if not authenticated, 403 if not admin)
    """
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    
    return SettingResponse(
        id=setting.id,
        key=setting.key,
        value=setting.value,
        description=setting.description,
        type=setting.type,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
        updated_by_user_id=setting.updated_by_user_id or "system",
    )


@router.post("")
async def update_settings(
    updates: List[SettingUpdateRequest],
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    """
    Bulk update settings and automatically reload cache.
    
    Args:
        updates: List of key-value pairs to update
    
    Returns:
        Status with count of updated settings
    
    Auth:
        Requires admin authentication (401 if not authenticated, 403 if not admin)
    
    Note:
        - Updates are atomic (all or nothing)
        - Cache is automatically reloaded after successful update
        - Unknown keys are ignored (no error)
    """
    try:
        updated_count = 0
        now = datetime.now(timezone.utc)
        
        for update in updates:
            setting = db.query(Setting).filter(Setting.key == update.key).first()
            if setting:
                setting.value = update.value
                setting.updated_at = now
                setting.updated_by_user_id = "admin"
                updated_count += 1
            else:
                logger.warning(f"Setting key '{update.key}' not found, skipping")
        
        db.commit()
        
        # Automatically reload cache after successful update
        cache_count = reload_settings_from_db(db)
        
        logger.info(
            f"Updated {updated_count} settings, reloaded {cache_count} into cache"
        )
        
        return {
            "status": "ok",
            "updated": updated_count,
            "cache_reloaded": cache_count,
            "message": f"Updated {updated_count} settings and reloaded cache",
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update settings")
