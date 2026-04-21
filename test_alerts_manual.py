"""
Manual test script for alert system.

Triggers various alert conditions and verifies they are logged and stored.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.models.database import SessionLocal, init_db
from backend.core.alert_manager import AlertManager, get_system_metrics


def test_alert_system():
    """Test the alert system with various conditions."""
    print("=" * 60)
    print("Alert System Test")
    print("=" * 60)
    
    init_db()
    db = SessionLocal()
    
    try:
        manager = AlertManager(db)
        
        print("\n1. Testing Circuit Breaker Alert...")
        alert = manager.check_circuit_breaker("polymarket_api", "open")
        if alert:
            print(f"   ✓ Alert created: {alert.message}")
        
        print("\n2. Testing Error Rate Alert...")
        for i in range(15):
            manager.record_error()
        alert = manager.check_error_rate()
        if alert:
            print(f"   ✓ Alert created: {alert.message}")
        
        print("\n3. Testing Memory Usage Alert...")
        alert = manager.check_memory_usage(85.0)
        if alert:
            print(f"   ✓ Alert created: {alert.message}")
        
        print("\n4. Testing Disk Space Alert...")
        alert = manager.check_disk_space(5.0)
        if alert:
            print(f"   ✓ Alert created: {alert.message}")
        
        print("\n5. Testing Connection Pool Alert...")
        alert = manager.check_connection_pool(pool_size=20, active_connections=20)
        if alert:
            print(f"   ✓ Alert created: {alert.message}")
        
        print("\n6. Getting System Metrics...")
        metrics = get_system_metrics()
        print(f"   Memory: {metrics['memory_percent']:.1f}%")
        print(f"   Disk Free: {metrics['disk_percent_free']:.1f}%")
        print(f"   DB Connections: {metrics['active_connections']}/{metrics['pool_size']}")
        
        print("\n7. Getting Recent Alerts...")
        alerts = manager.get_recent_alerts(limit=10)
        print(f"   Total alerts: {len(alerts)}")
        for alert in alerts[:5]:
            print(f"   - [{alert['severity']}] {alert['alert_type']}: {alert['message']}")
        
        print("\n8. Getting Alert Statistics...")
        stats = manager.get_alert_stats()
        print(f"   Total unresolved: {stats['total_unresolved']}")
        print(f"   By type: {stats['by_type']}")
        print(f"   By severity: {stats['by_severity']}")
        
        print("\n9. Testing Alert Cooldown...")
        alert1 = manager.check_memory_usage(90.0)
        alert2 = manager.check_memory_usage(90.0)
        print(f"   First alert: {'Created' if alert1 else 'None'}")
        print(f"   Second alert (should be None): {'Created' if alert2 else 'None (cooldown active)'}")
        
        print("\n" + "=" * 60)
        print("✓ Alert System Test Complete")
        print("=" * 60)
        
    finally:
        db.close()


if __name__ == "__main__":
    test_alert_system()
