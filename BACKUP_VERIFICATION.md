# Backup Verification System

## Overview
Comprehensive backup verification system that ensures database backups are complete, restorable, and maintain data integrity.

## Scripts

### 1. `backup_with_validation.sh` (242 lines)
Main backup creation script with integrated verification.

**Functions:**
- `verify_row_counts()` - Compares row counts across all tables
- `verify_schemas()` - Validates table schemas match using PRAGMA table_info
- `dry_run_restore()` - Tests restore by copying backup and checking integrity
- `run_backup_verification()` - Orchestrates all verification checks

**Output:**
- Backup file: `backups/auto_YYYYMMDD_HHMMSS.db`
- Logs: `logs/backup.log` and `logs/backup_verification.log`

**Verification Checks:**
1. Backup file exists and has size > 0
2. Backup can be read (SQLite integrity_check)
3. Dry-run restore test passes
4. All table schemas match
5. All table row counts match
6. Backup rotation (7-day retention)

### 2. `verify_latest_backup.sh` (172 lines)
Standalone verification script for hourly cron execution.

**Functions:**
- `verify_row_counts()` - Row count verification
- `verify_schemas()` - Schema verification
- `dry_run_restore()` - Restore test
- `find_latest_backup()` - Locates most recent backup
- `main()` - Orchestrates verification

**Output:**
- Logs: `logs/backup_verification.log`
- Alerts: `logs/backup_alerts.log` (with mail notification)

**Usage:**
```bash
bash scripts/verify_latest_backup.sh
```

### 3. `hourly_backup_job.sh` (46 lines)
Cron job wrapper that runs backup creation followed by verification.

**Flow:**
1. Runs `backup_with_validation.sh`
2. Runs `verify_latest_backup.sh`
3. Sends alerts on failure via mail

**Usage in crontab:**
```bash
0 * * * * /home/openclaw/projects/polyedge/scripts/hourly_backup_job.sh
```

### 4. `test_backup_verification.sh` (145 lines)
Comprehensive test demonstrating complete verification flow.

**Test Steps:**
1. Creates isolated test database with sample data
2. Creates backup
3. Verifies backup integrity
4. Tests dry-run restore
5. Verifies schemas match
6. Verifies row counts match
7. Verifies data integrity (sample queries)

**Test Results:**
```
✓ Backup file created and sized correctly
✓ Backup integrity check passed
✓ Dry-run restore test passed
✓ Schema verification passed
✓ Row count verification passed
✓ Data integrity verified
```

## Verification Checks Explained

### 1. Dry-Run Restore Test
- Copies backup to temporary location
- Runs `PRAGMA integrity_check` to verify database structure
- Counts accessible tables
- Cleans up temporary file

**Why:** Ensures backup can actually be restored and is not corrupted.

### 2. Schema Verification
- Compares `PRAGMA table_info()` for each table
- Verifies column names, types, and constraints match

**Why:** Detects schema corruption or incomplete backups.

### 3. Row Count Verification
- Counts rows in each table in original and backup
- Compares counts for exact match

**Why:** Detects data loss or incomplete backup creation.

### 4. Data Integrity Verification
- Runs sample queries (e.g., SUM calculations)
- Verifies results match between original and backup

**Why:** Detects data corruption at the value level.

## Log Files

### `logs/backup.log`
Main backup operation log with timestamps and status.

Example:
```
[2026-04-21 14:15:17] [INFO] Starting backup: /home/openclaw/projects/polyedge/backups/auto_20260421_141517.db
[2026-04-21 14:15:17] [INFO] Validating backup integrity
[2026-04-21 14:15:17] [INFO] Backup verified: 1519616 bytes, 48 trades, 29 tables
[2026-04-21 14:15:18] [INFO] Backup successful: /home/openclaw/projects/polyedge/backups/auto_20260421_141517.db
```

### `logs/backup_verification.log`
Detailed verification results for each check.

Example:
```
[2026-04-21 14:15:17] [INFO] ========== BACKUP VERIFICATION START ==========
[2026-04-21 14:15:17] [INFO] Starting dry-run restore test
[2026-04-21 14:15:17] [INFO] Dry-run restore test passed - 29 tables accessible
[2026-04-21 14:15:17] [INFO] Starting schema verification
[2026-04-21 14:15:17] [INFO] Table 'trades' schema verified
[2026-04-21 14:15:17] [INFO] Schema verification passed
[2026-04-21 14:15:17] [INFO] Starting row count verification
[2026-04-21 14:15:17] [INFO] Table 'trades': 48 rows (verified)
[2026-04-21 14:15:18] [INFO] Row count verification passed
[2026-04-21 14:15:18] [INFO] ========== BACKUP VERIFICATION PASSED ==========
```

### `logs/backup_alerts.log`
Critical alerts when verification fails.

Example:
```
[2026-04-21 14:15:26] ALERT: Row count verification failed for /home/openclaw/projects/polyedge/backups/auto_20260421_141517.db
[2026-04-21 14:15:26] ALERT: Backup verification failed - latest backup may be corrupted
```

## Integration with Cron

Add to crontab to run hourly:
```bash
crontab -e
# Add line:
0 * * * * /home/openclaw/projects/polyedge/scripts/hourly_backup_job.sh
```

This will:
- Create a backup at the top of each hour
- Verify the backup immediately after creation
- Log all results to `logs/backup.log` and `logs/backup_verification.log`
- Send mail alerts if verification fails

## Monitoring

### Check Latest Backup Status
```bash
tail -20 /home/openclaw/projects/polyedge/logs/backup_verification.log
```

### Check for Alerts
```bash
tail -10 /home/openclaw/projects/polyedge/logs/backup_alerts.log
```

### List Recent Backups
```bash
ls -lh /home/openclaw/projects/polyedge/backups/auto_*.db | tail -10
```

### Run Manual Verification
```bash
bash /home/openclaw/projects/polyedge/scripts/verify_latest_backup.sh
```

## Known Behavior

### Row Count Drift
If verification detects row count mismatches between original and backup:
- This is expected if the database receives writes after backup creation
- The backup represents a point-in-time snapshot
- Excessive drift (>100 rows) may indicate a problem

### Active Database
The system is designed to work with an active trading database:
- Backups are created while the database is in use
- Verification runs after backup creation
- Minor row count differences are normal and expected

## Troubleshooting

### Backup Verification Failed
1. Check `logs/backup_verification.log` for specific failure
2. Check `logs/backup_alerts.log` for alert details
3. Verify database is not corrupted: `sqlite3 tradingbot.db "PRAGMA integrity_check;"`
4. Check disk space: `df -h`

### Restore Test Failed
1. Verify backup file exists: `ls -lh backups/auto_*.db`
2. Test backup manually: `sqlite3 backups/auto_YYYYMMDD_HHMMSS.db "PRAGMA integrity_check;"`
3. Check for disk space issues

### Schema Mismatch
1. Verify database schema hasn't changed
2. Check for pending migrations
3. Restore from previous backup if schema is corrupted

## Performance

- Backup creation: ~1-2 seconds for 10MB database
- Verification: ~2-3 seconds (includes dry-run restore)
- Total hourly job: ~5 seconds
- Disk usage: 7-day retention = ~7 backups × database size

## Security

- Backups stored in `backups/` directory
- Verification logs contain no sensitive data
- Alert emails sent to root user
- Temporary restore files cleaned up automatically
