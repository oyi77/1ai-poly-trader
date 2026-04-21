#!/bin/bash
# Automated backup with validation and rotation

set -e

BACKUP_DIR="/home/openclaw/projects/polyedge/backups"
LOG_FILE="/home/openclaw/projects/polyedge/logs/backup.log"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/auto_$TIMESTAMP.db"
DB_FILE="/home/openclaw/projects/polyedge/tradingbot.db"
RETENTION_DAYS=7

# Ensure directories exist
mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log_message() {
    local level=$1
    local msg=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" >> "$LOG_FILE"
}

# Error handler
error_exit() {
    log_message "ERROR" "$1"
    exit 1
}

# Create backup
log_message "INFO" "Starting backup: $BACKUP_FILE"
if ! sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'" 2>/dev/null; then
    error_exit "Failed to create backup"
fi

# Verify backup file exists and has size > 0
if [ ! -f "$BACKUP_FILE" ]; then
    error_exit "Backup file not created: $BACKUP_FILE"
fi

BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null)
if [ "$BACKUP_SIZE" -le 0 ]; then
    rm -f "$BACKUP_FILE"
    error_exit "Backup file is empty or corrupted (size: $BACKUP_SIZE bytes)"
fi

# Validate backup integrity
log_message "INFO" "Validating backup integrity"

# Check row counts match
ORIGINAL_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
BACKUP_COUNT=$(sqlite3 "$BACKUP_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "-1")

if [ "$BACKUP_COUNT" = "-1" ]; then
    rm -f "$BACKUP_FILE"
    error_exit "Backup validation failed - cannot read backup database"
fi

if [ "$ORIGINAL_COUNT" != "$BACKUP_COUNT" ]; then
    rm -f "$BACKUP_FILE"
    error_exit "Backup validation failed - row count mismatch (original: $ORIGINAL_COUNT, backup: $BACKUP_COUNT)"
fi

# Check for table count consistency
ORIGINAL_TABLES=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "0")
BACKUP_TABLES=$(sqlite3 "$BACKUP_FILE" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "0")

if [ "$ORIGINAL_TABLES" != "$BACKUP_TABLES" ]; then
    rm -f "$BACKUP_FILE"
    error_exit "Backup validation failed - table count mismatch (original: $ORIGINAL_TABLES, backup: $BACKUP_TABLES)"
fi

log_message "INFO" "Backup verified: $BACKUP_SIZE bytes, $BACKUP_COUNT trades, $BACKUP_TABLES tables"

# Rotation: keep only backups from last 7 days
log_message "INFO" "Starting backup rotation (retention: $RETENTION_DAYS days)"
CUTOFF_TIME=$(date -d "$RETENTION_DAYS days ago" +%s 2>/dev/null || date -v-${RETENTION_DAYS}d +%s 2>/dev/null)

cd "$BACKUP_DIR"
DELETED_COUNT=0
for backup_file in auto_*.db; do
    if [ -f "$backup_file" ]; then
        FILE_TIME=$(stat -f%m "$backup_file" 2>/dev/null || stat -c%Y "$backup_file" 2>/dev/null)
        if [ "$FILE_TIME" -lt "$CUTOFF_TIME" ]; then
            rm -f "$backup_file"
            DELETED_COUNT=$((DELETED_COUNT + 1))
            log_message "INFO" "Deleted old backup: $backup_file"
        fi
    fi
done

REMAINING=$(ls -1 auto_*.db 2>/dev/null | wc -l)
log_message "INFO" "Rotation complete: deleted $DELETED_COUNT old backups, $REMAINING backups remaining"

log_message "INFO" "Backup successful: $BACKUP_FILE (size: $BACKUP_SIZE bytes)"
