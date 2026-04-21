#!/bin/bash
# Standalone backup verification script - runs as part of hourly cron job

set -e

BACKUP_DIR="/home/openclaw/projects/polyedge/backups"
DB_FILE="/home/openclaw/projects/polyedge/tradingbot.db"
VERIFICATION_LOG="/home/openclaw/projects/polyedge/logs/backup_verification.log"
ALERT_LOG="/home/openclaw/projects/polyedge/logs/backup_alerts.log"
TEMP_RESTORE_DB="/tmp/backup_verify_$$_$(date +%s).db"

log_verification() {
    local level=$1
    local msg=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" >> "$VERIFICATION_LOG"
}

log_alert() {
    local msg=$1
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] ALERT: $msg" >> "$ALERT_LOG"
}

cleanup() {
    rm -f "$TEMP_RESTORE_DB"
}

trap cleanup EXIT

verify_row_counts() {
    local original_db=$1
    local backup_db=$2
    local verification_passed=true
    
    log_verification "INFO" "Starting row count verification"
    
    local tables=$(sqlite3 "$original_db" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" 2>/dev/null)
    
    while IFS= read -r table; do
        [ -z "$table" ] && continue
        
        local orig_count=$(sqlite3 "$original_db" "SELECT COUNT(*) FROM \"$table\";" 2>/dev/null || echo "-1")
        local backup_count=$(sqlite3 "$backup_db" "SELECT COUNT(*) FROM \"$table\";" 2>/dev/null || echo "-1")
        
        if [ "$orig_count" = "-1" ] || [ "$backup_count" = "-1" ]; then
            log_verification "ERROR" "Failed to count rows in table: $table"
            verification_passed=false
        elif [ "$orig_count" != "$backup_count" ]; then
            log_verification "ERROR" "Row count mismatch in table '$table': original=$orig_count, backup=$backup_count"
            verification_passed=false
        else
            log_verification "INFO" "Table '$table': $orig_count rows (verified)"
        fi
    done <<< "$tables"
    
    if [ "$verification_passed" = true ]; then
        log_verification "INFO" "Row count verification passed"
        return 0
    else
        log_verification "ERROR" "Row count verification failed"
        return 1
    fi
}

verify_schemas() {
    local original_db=$1
    local backup_db=$2
    local verification_passed=true
    
    log_verification "INFO" "Starting schema verification"
    
    local tables=$(sqlite3 "$original_db" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" 2>/dev/null)
    
    while IFS= read -r table; do
        [ -z "$table" ] && continue
        
        local orig_schema=$(sqlite3 "$original_db" "PRAGMA table_info(\"$table\");" 2>/dev/null)
        local backup_schema=$(sqlite3 "$backup_db" "PRAGMA table_info(\"$table\");" 2>/dev/null)
        
        if [ "$orig_schema" != "$backup_schema" ]; then
            log_verification "ERROR" "Schema mismatch in table '$table'"
            verification_passed=false
        else
            log_verification "INFO" "Table '$table' schema verified"
        fi
    done <<< "$tables"
    
    if [ "$verification_passed" = true ]; then
        log_verification "INFO" "Schema verification passed"
        return 0
    else
        log_verification "ERROR" "Schema verification failed"
        return 1
    fi
}

dry_run_restore() {
    local backup_db=$1
    local temp_restore=$2
    
    log_verification "INFO" "Starting dry-run restore test"
    
    if ! cp "$backup_db" "$temp_restore" 2>/dev/null; then
        log_verification "ERROR" "Failed to copy backup for restore test"
        return 1
    fi
    
    if ! sqlite3 "$temp_restore" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
        log_verification "ERROR" "Restore test failed - database integrity check failed"
        return 1
    fi
    
    local table_count=$(sqlite3 "$temp_restore" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "0")
    if [ "$table_count" -eq 0 ]; then
        log_verification "ERROR" "Restore test failed - no tables found in restored database"
        return 1
    fi
    
    log_verification "INFO" "Dry-run restore test passed - $table_count tables accessible"
    return 0
}

find_latest_backup() {
    local latest=$(ls -t "$BACKUP_DIR"/auto_*.db 2>/dev/null | head -1)
    if [ -z "$latest" ]; then
        log_verification "ERROR" "No backup files found in $BACKUP_DIR"
        return 1
    fi
    echo "$latest"
}

main() {
    log_verification "INFO" "========== HOURLY BACKUP VERIFICATION START =========="
    
    local latest_backup=$(find_latest_backup)
    if [ $? -ne 0 ]; then
        log_alert "No backup files found for verification"
        return 1
    fi
    
    log_verification "INFO" "Verifying latest backup: $latest_backup"
    
    local all_passed=true
    
    if ! dry_run_restore "$latest_backup" "$TEMP_RESTORE_DB"; then
        all_passed=false
        log_alert "Dry-run restore test failed for $latest_backup"
    fi
    
    if ! verify_schemas "$DB_FILE" "$latest_backup"; then
        all_passed=false
        log_alert "Schema verification failed for $latest_backup"
    fi
    
    if ! verify_row_counts "$DB_FILE" "$latest_backup"; then
        all_passed=false
        log_alert "Row count verification failed for $latest_backup"
    fi
    
    if [ "$all_passed" = true ]; then
        log_verification "INFO" "========== HOURLY BACKUP VERIFICATION PASSED =========="
        return 0
    else
        log_verification "ERROR" "========== HOURLY BACKUP VERIFICATION FAILED =========="
        log_alert "Backup verification failed - latest backup may be corrupted"
        return 1
    fi
}

main
exit $?
