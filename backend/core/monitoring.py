"""
Production monitoring and alerting system
Detects anomalies and sends alerts
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("trading_bot")

class ProductionMonitor:
    """Monitor production health and detect issues"""
    
    def __init__(self, db: Session):
        self.db = db
        self.alerts = []
    
    def check_database_health(self) -> Dict[str, Any]:
        """Check database for anomalies"""
        issues = []
        
        # Check for duplicates
        duplicates = self.db.execute(text("""
            SELECT market_ticker, COUNT(*) as count 
            FROM trades 
            WHERE trading_mode = 'live' 
            GROUP BY market_ticker 
            HAVING count > 1
        """)).fetchall()
        
        if duplicates:
            issues.append({
                "severity": "high",
                "type": "duplicates",
                "message": f"Found {len(duplicates)} duplicate trades",
                "details": [{"ticker": d[0], "count": d[1]} for d in duplicates]
            })
        
        # Check database size
        db_size = self.db.execute(text("""
            SELECT COUNT(*) FROM trades
        """)).fetchone()[0]
        
        if db_size < 10:
            issues.append({
                "severity": "critical",
                "type": "database_wipe",
                "message": f"Database suspiciously small: only {db_size} trades",
                "details": {"trade_count": db_size}
            })
        
        # Check for missing PNL
        missing_pnl = self.db.execute(text("""
            SELECT COUNT(*) 
            FROM trades 
            WHERE settled = 1 AND pnl IS NULL
        """)).fetchone()[0]
        
        if missing_pnl > 0:
            issues.append({
                "severity": "medium",
                "type": "missing_pnl",
                "message": f"{missing_pnl} settled trades missing PNL",
                "details": {"count": missing_pnl}
            })
        
        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
    
    def check_pnl_accuracy(self) -> Dict[str, Any]:
        """Verify PNL matches Polymarket"""
        # This would fetch from Polymarket API and compare
        # For now, just return placeholder
        return {
            "accurate": True,
            "message": "PNL accuracy check not yet implemented"
        }
    
    def check_backup_status(self) -> Dict[str, Any]:
        """Check if backups are running"""
        import os
        from pathlib import Path
        
        backup_dir = Path("/home/openclaw/projects/polyedge/backups")
        if not backup_dir.exists():
            return {
                "healthy": False,
                "message": "Backup directory not found"
            }
        
        # Check for recent backups
        backups = sorted(backup_dir.glob("auto_*.db"), key=os.path.getmtime, reverse=True)
        
        if not backups:
            return {
                "healthy": False,
                "message": "No backups found"
            }
        
        latest_backup = backups[0]
        backup_age = datetime.now().timestamp() - os.path.getmtime(latest_backup)
        
        # Alert if backup is older than 2 hours
        if backup_age > 7200:
            return {
                "healthy": False,
                "message": f"Latest backup is {backup_age/3600:.1f} hours old",
                "latest_backup": str(latest_backup)
            }
        
        return {
            "healthy": True,
            "message": f"Latest backup: {backup_age/60:.0f} minutes ago",
            "backup_count": len(backups),
            "latest_backup": str(latest_backup)
        }
    
    def run_health_check(self) -> Dict[str, Any]:
        """Run all health checks"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": self.check_database_health(),
            "pnl_accuracy": self.check_pnl_accuracy(),
            "backups": self.check_backup_status()
        }
    
    def send_alert(self, severity: str, message: str, details: Optional[Dict] = None):
        """Send alert (placeholder for Slack/Discord integration)"""
        alert = {
            "severity": severity,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.warning(f"🚨 ALERT [{severity}]: {message}")
        if details:
            logger.warning(f"   Details: {details}")
        
        self.alerts.append(alert)
        
        # TODO: Send to Slack/Discord
        # await send_to_slack(alert)
        
        return alert


async def run_monitoring_check(db: Session) -> Dict[str, Any]:
    """Run monitoring check and return results"""
    monitor = ProductionMonitor(db)
    health = monitor.run_health_check()
    
    # Send alerts for critical issues
    if not health['database']['healthy']:
        for issue in health['database']['issues']:
            if issue['severity'] in ['critical', 'high']:
                monitor.send_alert(
                    issue['severity'],
                    issue['message'],
                    issue.get('details')
                )
    
    if not health['backups']['healthy']:
        monitor.send_alert(
            'high',
            health['backups']['message']
        )
    
    return health
