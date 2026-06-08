#!/usr/bin/env python3
"""
24-hour paper trading monitor.
Runs every hour, logs PnL, trade count, and strategy status.
Usage: python scripts/monitor_24h.py
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings
from backend.models.database import BotState, Trade, SessionLocal
from sqlalchemy import func

LOG_FILE = Path("logs/monitor_24h.csv")

def get_snapshot():
    session = SessionLocal()
    try:
        state = session.query(BotState).filter_by(mode="paper").first()
        bankroll = state.bankroll if state else 0.0
        
        total_trades = session.query(func.count(Trade.id)).filter(Trade.settled == True).scalar() or 0
        total_pnl = session.query(func.coalesce(func.sum(Trade.pnl), 0.0)).filter(Trade.settled == True).scalar() or 0.0
        wins = session.query(func.count(Trade.id)).filter(Trade.settled == True, Trade.pnl > 0).scalar() or 0
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bankroll": bankroll,
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "wins": wins,
            "win_rate": (wins / total_trades * 100) if total_trades > 0 else 0.0,
        }
    finally:
        session.close()

def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Write header if file doesn't exist
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w") as f:
            f.write("timestamp,bankroll,total_trades,total_pnl,wins,win_rate\n")
    
    print(f"24h Paper Trading Monitor")
    print(f"Logging to: {LOG_FILE}")
    print(f"Press Ctrl+C to stop")
    print()
    
    try:
        while True:
            snap = get_snapshot()
            
            # Log to CSV
            with open(LOG_FILE, "a") as f:
                f.write(f"{snap['timestamp']},{snap['bankroll']:.2f},{snap['total_trades']},{snap['total_pnl']:.2f},{snap['wins']},{snap['win_rate']:.1f}\n")
            
            # Print summary
            print(f"[{snap['timestamp'][:19]}] "
                  f"Bankroll: ${snap['bankroll']:.2f} | "
                  f"Trades: {snap['total_trades']} | "
                  f"PnL: ${snap['total_pnl']:+.2f} | "
                  f"WR: {snap['win_rate']:.1f}%")
            
            time.sleep(3600)  # Wait 1 hour
            
    except KeyboardInterrupt:
        print("\nMonitor stopped.")

if __name__ == "__main__":
    main()
