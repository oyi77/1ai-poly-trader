"""Alert manager for detecting and reporting critical conditions."""

import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from backend.models.database import Alert, AlertConfig

logger = logging.getLogger("alert_manager")


class AlertManager:
    """Manages alert detection and logging for critical conditions."""
    
    def __init__(self, db: Session):
        self.db = db
        self._ensure_default_config()
    
    def _ensure_default_config(self):
        """Initialize default alert configurations if not present."""
        defaults = [
            ("NEGATIVE_BALANCE", True, 0.0, "absolute", "CRITICAL"),
            ("POSITION_DISCREPANCY", True, 0.05, "percent", "WARNING"),
            ("FAILED_SETTLEMENT", True, None, None, "CRITICAL"),
            ("HIGH_SLIPPAGE", True, 0.01, "percent", "WARNING"),
        ]
        
        for alert_type, enabled, threshold, unit, severity in defaults:
            existing = self.db.query(AlertConfig).filter_by(alert_type=alert_type).first()
            if not existing:
                config = AlertConfig(
                    alert_type=alert_type,
                    enabled=enabled,
                    threshold_value=threshold,
                    threshold_unit=unit,
                    severity=severity,
                )
                self.db.add(config)
        
        try:
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to initialize alert config: {e}")
            self.db.rollback()
    
    def check_negative_balance(self, wallet_id: str, balance: float, mode: str) -> Optional[Alert]:
        """Check for negative balance condition."""
        config = self.db.query(AlertConfig).filter_by(alert_type="NEGATIVE_BALANCE").first()
        if not config or not config.enabled:
            return None
        
        if balance < 0:
            message = f"Negative balance detected: {mode} wallet {wallet_id} has balance ${balance:.2f}"
            alert = self._create_alert(
                alert_type="NEGATIVE_BALANCE",
                severity=config.severity,
                entity_type="WALLET",
                entity_id=wallet_id,
                message=message,
            )
            logger.critical(message)
            return alert
        
        return None
    
    def check_position_discrepancy(
        self, 
        position_id: str, 
        db_value: float, 
        blockchain_value: float,
        mode: str
    ) -> Optional[Alert]:
        """Check for position discrepancy between DB and blockchain."""
        config = self.db.query(AlertConfig).filter_by(alert_type="POSITION_DISCREPANCY").first()
        if not config or not config.enabled:
            return None
        
        if db_value == 0 and blockchain_value == 0:
            return None
        
        threshold = config.threshold_value or 0.05
        discrepancy = abs(db_value - blockchain_value) / max(db_value, blockchain_value, 1.0)
        
        if discrepancy > threshold:
            message = (
                f"Position discrepancy detected: {mode} position {position_id} "
                f"DB=${db_value:.2f} vs Blockchain=${blockchain_value:.2f} "
                f"({discrepancy:.1%} > {threshold:.1%} threshold)"
            )
            alert = self._create_alert(
                alert_type="POSITION_DISCREPANCY",
                severity=config.severity,
                entity_type="POSITION",
                entity_id=position_id,
                message=message,
            )
            logger.warning(message)
            return alert
        
        return None
    
    def check_failed_settlement(self, trade_id: int, reason: str, mode: str) -> Optional[Alert]:
        """Check for failed settlement."""
        config = self.db.query(AlertConfig).filter_by(alert_type="FAILED_SETTLEMENT").first()
        if not config or not config.enabled:
            return None
        
        message = f"Settlement failed: {mode} trade {trade_id} - {reason}"
        alert = self._create_alert(
            alert_type="FAILED_SETTLEMENT",
            severity=config.severity,
            entity_type="TRADE",
            entity_id=str(trade_id),
            message=message,
        )
        logger.critical(message)
        return alert
    
    def check_high_slippage(
        self, 
        trade_id: int, 
        expected_price: float, 
        actual_price: float,
        position_value: float,
        mode: str
    ) -> Optional[Alert]:
        """Check for high slippage on order execution."""
        config = self.db.query(AlertConfig).filter_by(alert_type="HIGH_SLIPPAGE").first()
        if not config or not config.enabled:
            return None
        
        threshold = config.threshold_value or 0.01
        slippage = abs(expected_price - actual_price) / expected_price if expected_price > 0 else 0
        slippage_value = slippage * position_value
        
        if slippage > threshold:
            message = (
                f"High slippage detected: {mode} trade {trade_id} "
                f"expected ${expected_price:.4f} got ${actual_price:.4f} "
                f"({slippage:.2%} > {threshold:.2%} threshold, ${slippage_value:.2f} impact)"
            )
            alert = self._create_alert(
                alert_type="HIGH_SLIPPAGE",
                severity=config.severity,
                entity_type="TRADE",
                entity_id=str(trade_id),
                message=message,
            )
            logger.warning(message)
            return alert
        
        return None
    
    def _create_alert(
        self,
        alert_type: str,
        severity: str,
        entity_type: str,
        entity_id: str,
        message: str,
    ) -> Alert:
        """Create and persist an alert record."""
        alert = Alert(
            timestamp=datetime.now(timezone.utc),
            alert_type=alert_type,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            resolved=False,
        )
        
        self.db.add(alert)
        try:
            self.db.commit()
            self.db.refresh(alert)
        except Exception as e:
            logger.error(f"Failed to persist alert: {e}")
            self.db.rollback()
        
        return alert
    
    def resolve_alert(self, alert_id: int) -> bool:
        """Mark an alert as resolved."""
        alert = self.db.query(Alert).filter_by(id=alert_id).first()
        if not alert:
            return False
        
        alert.resolved = True
        alert.resolved_at = datetime.now(timezone.utc)
        
        try:
            self.db.commit()
            logger.info(f"Alert {alert_id} resolved")
            return True
        except Exception as e:
            logger.error(f"Failed to resolve alert {alert_id}: {e}")
            self.db.rollback()
            return False
