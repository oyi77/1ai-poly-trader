"""Alert model for monitoring critical conditions."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Index
from backend.models.database import Base


class Alert(Base):
    """Alert records for critical conditions."""
    
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    alert_type = Column(String, nullable=False, index=True)  # NEGATIVE_BALANCE, POSITION_DISCREPANCY, FAILED_SETTLEMENT, HIGH_SLIPPAGE
    severity = Column(String, nullable=False)  # CRITICAL, WARNING, INFO
    entity_type = Column(String, nullable=False)  # WALLET, POSITION, TRADE
    entity_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("idx_alerts_type_severity", "alert_type", "severity"),
        Index("idx_alerts_resolved", "resolved"),
    )
    
    def __repr__(self):
        return (
            f"<Alert(id={self.id}, type={self.alert_type}, severity={self.severity}, "
            f"entity={self.entity_type}:{self.entity_id}, resolved={self.resolved})>"
        )


class AlertConfig(Base):
    """Configurable alert thresholds."""
    
    __tablename__ = "alert_config"
    
    id = Column(Integer, primary_key=True)
    alert_type = Column(String, unique=True, nullable=False)
    enabled = Column(Boolean, default=True)
    threshold_value = Column(Float, nullable=True)  # Numeric threshold (e.g., 0.05 for 5%)
    threshold_unit = Column(String, nullable=True)  # "percent", "absolute", "count"
    severity = Column(String, default="WARNING")  # Default severity level
    
    def __repr__(self):
        return (
            f"<AlertConfig(type={self.alert_type}, enabled={self.enabled}, "
            f"threshold={self.threshold_value} {self.threshold_unit})>"
        )
