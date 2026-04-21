"""Settings API endpoints for system configuration."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from backend.api.auth import require_admin
from backend.models.database import get_db, SystemSettings
from backend.config import settings as app_settings

logger = logging.getLogger("trading_bot")

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    mirofish_enabled: bool
    mirofish_api_url: Optional[str]
    mirofish_api_key: Optional[str]
    strategies: Dict[str, bool]
    risk_params: Dict[str, Any]
    trading_mode: str


class SettingsUpdateRequest(BaseModel):
    mirofish_enabled: Optional[bool] = None
    mirofish_api_url: Optional[str] = None
    mirofish_api_key: Optional[str] = None
    strategies: Optional[Dict[str, bool]] = None
    risk_params: Optional[Dict[str, Any]] = None
    trading_mode: Optional[str] = None


class ToggleResponse(BaseModel):
    enabled: bool
    message: str


def _get_setting(db: Session, key: str, default: Any = None) -> Any:
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    if setting:
        return setting.value
    return default


def _set_setting(db: Session, key: str, value: Any):
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    if setting:
        setting.value = value
        setting.updated_at = datetime.now(timezone.utc)
    else:
        setting = SystemSettings(key=key, value=value)
        db.add(setting)


@router.get("", response_model=SettingsResponse)
async def get_settings(db: Session = Depends(get_db)):
    try:
        mirofish_enabled = _get_setting(db, "mirofish_enabled", False)
        mirofish_api_url = _get_setting(db, "mirofish_api_url", None)
        mirofish_api_key = _get_setting(db, "mirofish_api_key", None)
        strategies = _get_setting(db, "strategies_enabled", {})
        risk_params = _get_setting(db, "risk_params", {
            "max_position_size": app_settings.MAX_TRADE_SIZE,
            "max_daily_loss": app_settings.DAILY_LOSS_LIMIT,
            "max_total_pending": app_settings.MAX_TOTAL_PENDING_TRADES,
        })
        trading_mode = _get_setting(db, "trading_mode", app_settings.TRADING_MODE)
        
        return SettingsResponse(
            mirofish_enabled=mirofish_enabled,
            mirofish_api_url=mirofish_api_url,
            mirofish_api_key=mirofish_api_key,
            strategies=strategies,
            risk_params=risk_params,
            trading_mode=trading_mode,
        )
    except Exception as e:
        logger.error(f"Failed to get settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve settings")


@router.put("")
async def update_settings(
    updates: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    from backend.models.audit_logger import log_audit_event
    
    try:
        # Track changes for audit logging
        changes = {}
        
        if updates.mirofish_enabled is not None:
            old_value = _get_setting(db, "mirofish_enabled", False)
            _set_setting(db, "mirofish_enabled", updates.mirofish_enabled)
            changes["mirofish_enabled"] = {"old": old_value, "new": updates.mirofish_enabled}
        
        if updates.mirofish_api_url is not None:
            old_value = _get_setting(db, "mirofish_api_url", None)
            _set_setting(db, "mirofish_api_url", updates.mirofish_api_url)
            changes["mirofish_api_url"] = {"old": old_value, "new": "[REDACTED]"}
        
        if updates.mirofish_api_key is not None:
            old_value = _get_setting(db, "mirofish_api_key", None)
            _set_setting(db, "mirofish_api_key", updates.mirofish_api_key)
            changes["mirofish_api_key"] = {"old": "[REDACTED]", "new": "[REDACTED]"}
        
        if updates.strategies is not None:
            old_value = _get_setting(db, "strategies_enabled", {})
            _set_setting(db, "strategies_enabled", updates.strategies)
            changes["strategies_enabled"] = {"old": old_value, "new": updates.strategies}
        
        if updates.risk_params is not None:
            old_value = _get_setting(db, "risk_params", {})
            _set_setting(db, "risk_params", updates.risk_params)
            changes["risk_params"] = {"old": old_value, "new": updates.risk_params}
        
        if updates.trading_mode is not None:
            if updates.trading_mode not in ["paper", "testnet", "live"]:
                raise HTTPException(status_code=400, detail="Invalid trading mode")
            old_value = _get_setting(db, "trading_mode", app_settings.TRADING_MODE)
            _set_setting(db, "trading_mode", updates.trading_mode)
            changes["trading_mode"] = {"old": old_value, "new": updates.trading_mode}
        
        # Log audit event for configuration changes
        if changes:
            log_audit_event(
                db=db,
                event_type="CONFIG_UPDATED",
                entity_type="SYSTEM_SETTINGS",
                entity_id="global",
                old_value={"changes": {k: v["old"] for k, v in changes.items()}},
                new_value={"changes": {k: v["new"] for k, v in changes.items()}},
                user_id="admin",
            )
        
        db.commit()
        logger.info("Settings updated successfully")
        
        return {"status": "ok", "message": "Settings updated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update settings")


@router.post("/mirofish/toggle", response_model=ToggleResponse)
async def toggle_mirofish(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    from backend.models.audit_logger import log_audit_event
    
    try:
        current = _get_setting(db, "mirofish_enabled", False)
        new_state = not current
        _set_setting(db, "mirofish_enabled", new_state)
        
        log_audit_event(
            db=db,
            event_type="MIROFISH_TOGGLE",
            entity_type="CONFIG",
            entity_id="mirofish_enabled",
            old_value={"enabled": current},
            new_value={"enabled": new_state},
            user_id="admin",
        )
        
        db.commit()
        
        logger.info(f"MiroFish toggled: {current} -> {new_state}")
        
        return ToggleResponse(
            enabled=new_state,
            message=f"MiroFish {'enabled' if new_state else 'disabled'}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to toggle MiroFish: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to toggle MiroFish")


@router.post("/strategy/{name}/toggle", response_model=ToggleResponse)
async def toggle_strategy(
    name: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin)
):
    from backend.models.audit_logger import log_audit_event
    
    try:
        strategies = _get_setting(db, "strategies_enabled", {})
        current = strategies.get(name, False)
        new_state = not current
        strategies[name] = new_state
        _set_setting(db, "strategies_enabled", strategies)
        
        log_audit_event(
            db=db,
            event_type="STRATEGY_TOGGLE",
            entity_type="STRATEGY_CONFIG",
            entity_id=name,
            old_value={"enabled": current},
            new_value={"enabled": new_state},
            user_id="admin",
        )
        
        db.commit()
        
        logger.info(f"Strategy '{name}' toggled: {current} -> {new_state}")
        
        return ToggleResponse(
            enabled=new_state,
            message=f"Strategy '{name}' {'enabled' if new_state else 'disabled'}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to toggle strategy '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to toggle strategy '{name}'")
