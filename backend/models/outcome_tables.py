from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, Text, ForeignKey
from backend.models.database import Base


class StrategyOutcome(Base):
    __tablename__ = 'strategy_outcomes'

    id = Column(Integer, primary_key=True)
    strategy = Column(String, nullable=False)
    market_ticker = Column(String, nullable=False)
    market_type = Column(String, nullable=False)
    trading_mode = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    model_probability = Column(Float, nullable=True)
    market_price = Column(Float, nullable=True)
    edge_at_entry = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    result = Column(String, nullable=True)
    pnl = Column(Float, nullable=True)
    reward = Column(Float, nullable=True)
    settled_at = Column(DateTime, nullable=True)
    trade_id = Column(Integer, ForeignKey('trades.id'), nullable=False)


class ParamChange(Base):
    __tablename__ = 'param_changes'

    id = Column(Integer, primary_key=True)
    strategy = Column(String, nullable=False)
    param_name = Column(String, nullable=False)
    old_value = Column(Float, nullable=True)
    new_value = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reverted_at = Column(DateTime, nullable=True)
    pre_change_sharpe = Column(Float, nullable=True)
    post_change_sharpe = Column(Float, nullable=True)
    auto_applied = Column(Boolean, nullable=False, default=False)


class StrategyHealthRecord(Base):
    __tablename__ = 'strategy_health'

    id = Column(Integer, primary_key=True)
    strategy = Column(String, nullable=False)
    total_trades = Column(Integer, nullable=False, default=0)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    win_rate = Column(Float, nullable=False, default=0.0)
    sharpe = Column(Float, nullable=False, default=0.0)
    max_drawdown = Column(Float, nullable=True)
    brier_score = Column(Float, nullable=True)
    psi_score = Column(Float, nullable=True)
    status = Column(String, nullable=False, default='active')
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow)


class TradingCalibrationRecord(Base):
    __tablename__ = 'trading_calibration_records'

    id = Column(Integer, primary_key=True)
    strategy = Column(String, nullable=False)
    predicted_prob = Column(Float, nullable=False)
    actual_outcome = Column(Integer, nullable=False)
    brier_score = Column(Float, nullable=True)
    market_type = Column(String, nullable=False, default='unknown')
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)