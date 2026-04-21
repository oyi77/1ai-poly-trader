# Database Backup Automation Setup

## Overview
Hourly automated backups with 7-day rotation and corruption detection.

## Quick Start

### Option 1: Cron Job (Recommended for simplicity)
```bash
/home/openclaw/projects/polyedge/scripts/backup-cron.sh
```

### Option 2: Systemd Timer (Recommended for production)
```bash
sudo cp /home/openclaw/projects/polyedge/scripts/polyedge-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable polyedge-backup.timer
sudo systemctl start polyedge-backup.timer
```

## Verification

Check cron installation:
```bash
crontab -l | grep backup_with_validation.sh
```

Check systemd timer:
```bash
sudo systemctl status polyedge-backup.timer
sudo systemctl list-timers polyedge-backup.timer
```

## Monitoring

View backup logs:
```bash
tail -f /home/openclaw/projects/polyedge/logs/backup.log
```

List recent backups:
```bash
ls -lh /home/openclaw/projects/polyedge/backups/ | head -10
```

## Features

- **Hourly Backups**: Runs at the top of every hour
- **7-Day Rotation**: Keeps last 7 days of backups (~168 files)
- **Corruption Detection**: Verifies file size, row count, table count
- **Structured Logging**: All operations logged with timestamps
- **Error Handling**: Removes corrupt backups, logs errors
- **Portable**: Works on Linux/Unix with bash and sqlite3

## Backup Details

- **Location**: `/home/openclaw/projects/polyedge/backups/`
- **Naming**: `auto_YYYYMMDD_HHMMSS.db`
- **Log File**: `/home/openclaw/projects/polyedge/logs/backup.log`
- **Retention**: 7 days (168 hourly backups)
- **Estimated Size**: ~7GB (at ~40MB per backup)

## Troubleshooting

### Backups not running
1. Check cron: `crontab -l`
2. Check systemd: `sudo systemctl status polyedge-backup.timer`
3. Check logs: `tail -f /home/openclaw/projects/polyedge/logs/backup.log`

### Backup verification failures
- Check database integrity: `sqlite3 /home/openclaw/projects/polyedge/tradingbot.db "PRAGMA integrity_check;"`
- Check disk space: `df -h /home/openclaw/projects/polyedge/`
- Check permissions: `ls -ld /home/openclaw/projects/polyedge/backups/`

### Manual backup
```bash
/home/openclaw/projects/polyedge/scripts/backup_with_validation.sh
```

## Recovery

Restore from backup:
```bash
cp /home/openclaw/projects/polyedge/backups/auto_YYYYMMDD_HHMMSS.db /home/openclaw/projects/polyedge/tradingbot.db
```

Verify restored database:
```bash
sqlite3 /home/openclaw/projects/polyedge/tradingbot.db "SELECT COUNT(*) FROM trades;"
```
