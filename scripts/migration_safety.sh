#!/bin/bash
# Migration Safety Script - Backup, Rollback, and Verification for Database Migrations
# 
# PURPOSE:
#   Provides bulletproof backup/rollback functions for database schema migrations.
#   Prevents data loss by creating timestamped backups and enabling point-in-time recovery.
#
# USAGE:
#   ./scripts/migration_safety.sh backup              # Create timestamped backup
#   ./scripts/migration_safety.sh rollback <backup>   # Restore from backup file
#   ./scripts/migration_safety.sh verify <backup>     # Verify backup integrity
#   ./scripts/migration_safety.sh pre-check           # Run pre-migration checks
#
# EXAMPLES:
#   # Create backup before migration
#   ./scripts/migration_safety.sh backup
#   
#   # Rollback if migration fails
#   ./scripts/migration_safety.sh rollback backups/polyedge-20260420_224431.db
#   
#   # Verify backup before using it
#   ./scripts/migration_safety.sh verify backups/polyedge-20260420_224431.db
#   
#   # Run all pre-migration checks
#   ./scripts/migration_safety.sh pre-check

set -euo pipefail

# Configuration
PROJECT_ROOT="/home/openclaw/projects/polyedge"
DB_FILE="$PROJECT_ROOT/tradingbot.db"
BACKUP_DIR="$PROJECT_ROOT/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/polyedge-$TIMESTAMP.db"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_db_exists() {
    if [ ! -f "$DB_FILE" ]; then
        log_error "Database not found: $DB_FILE"
        exit 1
    fi
}

check_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        log_info "Creating backup directory: $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
    fi
}

# ============================================================================
# BACKUP FUNCTION
# ============================================================================

backup_database() {
    log_info "Starting database backup..."
    
    check_db_exists
    check_backup_dir
    
    # Get pre-backup stats
    local pre_backup_tables=$(sqlite3 "$DB_FILE" ".tables" | wc -w)
    local pre_backup_trades=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
    
    log_info "Pre-backup: $pre_backup_tables tables, $pre_backup_trades trades"
    
    # Create backup using SQLite backup command
    if sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"; then
        log_info "Backup created: $BACKUP_FILE"
    else
        log_error "Failed to create backup"
        exit 1
    fi
    
    # Verify backup file exists and has content
    if [ ! -f "$BACKUP_FILE" ]; then
        log_error "Backup file not created"
        exit 1
    fi
    
    local backup_size=$(du -h "$BACKUP_FILE" | cut -f1)
    log_info "Backup size: $backup_size"
    
    # Validate backup integrity
    local post_backup_tables=$(sqlite3 "$BACKUP_FILE" ".tables" | wc -w)
    local post_backup_trades=$(sqlite3 "$BACKUP_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
    
    if [ "$pre_backup_tables" != "$post_backup_tables" ]; then
        log_error "Table count mismatch: $pre_backup_tables vs $post_backup_tables"
        rm "$BACKUP_FILE"
        exit 1
    fi
    
    if [ "$pre_backup_trades" != "$post_backup_trades" ]; then
        log_error "Trade count mismatch: $pre_backup_trades vs $post_backup_trades"
        rm "$BACKUP_FILE"
        exit 1
    fi
    
    log_info "Backup validation passed"
    
    # Create symlink to latest backup
    ln -sf "$BACKUP_FILE" "$BACKUP_DIR/latest.db"
    log_info "Latest backup symlink updated"
    
    echo "$BACKUP_FILE"
}

# ============================================================================
# ROLLBACK FUNCTION
# ============================================================================

rollback_database() {
    local backup_file="$1"
    
    if [ -z "$backup_file" ]; then
        log_error "Usage: rollback_database <backup_file>"
        exit 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        exit 1
    fi
    
    check_db_exists
    
    log_warn "Rolling back database from: $backup_file"
    
    # Get pre-rollback stats
    local pre_rollback_trades=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
    log_info "Pre-rollback: $pre_rollback_trades trades"
    
    # Create safety backup of current state before rollback
    local safety_backup="$BACKUP_DIR/pre-rollback-$TIMESTAMP.db"
    if sqlite3 "$DB_FILE" ".backup '$safety_backup'"; then
        log_info "Safety backup created: $safety_backup"
    else
        log_error "Failed to create safety backup"
        exit 1
    fi
    
    # Restore from backup
    if sqlite3 "$DB_FILE" ".restore '$backup_file'"; then
        log_info "Database restored from backup"
    else
        log_error "Failed to restore from backup"
        log_warn "Safety backup available at: $safety_backup"
        exit 1
    fi
    
    # Verify rollback
    local post_rollback_trades=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
    log_info "Post-rollback: $post_rollback_trades trades"
    
    log_info "Rollback completed successfully"
}

# ============================================================================
# VERIFY FUNCTION
# ============================================================================

verify_migration() {
    local backup_file="${1:-$DB_FILE}"
    
    if [ ! -f "$backup_file" ]; then
        log_error "File not found: $backup_file"
        exit 1
    fi
    
    log_info "Verifying: $backup_file"
    
    # Get table list
    local tables=$(sqlite3 "$backup_file" ".tables")
    local table_count=$(echo "$tables" | wc -w)
    log_info "Tables ($table_count): $tables"
    
    # Get row counts for key tables
    local trades_count=$(sqlite3 "$backup_file" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
    local signals_count=$(sqlite3 "$backup_file" "SELECT COUNT(*) FROM signals;" 2>/dev/null || echo "0")
    local orders_count=$(sqlite3 "$backup_file" "SELECT COUNT(*) FROM orders;" 2>/dev/null || echo "0")
    
    log_info "Row counts:"
    log_info "  - trades: $trades_count"
    log_info "  - signals: $signals_count"
    log_info "  - orders: $orders_count"
    
    # Check for corruption
    if sqlite3 "$backup_file" "PRAGMA integrity_check;" | grep -q "ok"; then
        log_info "Integrity check: PASSED"
    else
        log_error "Integrity check: FAILED"
        exit 1
    fi
    
    log_info "Verification completed successfully"
}

# ============================================================================
# PRE-MIGRATION CHECKS
# ============================================================================

pre_migration_checks() {
    log_info "Running pre-migration checks..."
    
    check_db_exists
    check_backup_dir
    
    # Check 1: Active trades
    log_info "Check 1: Checking for active trades..."
    local active_trades=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades WHERE status='open';" 2>/dev/null || echo "0")
    if [ "$active_trades" -gt 0 ]; then
        log_warn "Found $active_trades active trades - consider closing before migration"
    else
        log_info "No active trades found"
    fi
    
    # Check 2: Disk space
    log_info "Check 2: Checking disk space..."
    local available_space=$(df "$BACKUP_DIR" | awk 'NR==2 {print $4}')
    local db_size=$(du -k "$DB_FILE" | cut -f1)
    local required_space=$((db_size * 2))  # Need 2x for backup + safety margin
    
    if [ "$available_space" -lt "$required_space" ]; then
        log_error "Insufficient disk space: need ${required_space}KB, have ${available_space}KB"
        exit 1
    fi
    log_info "Disk space OK: ${available_space}KB available"
    
    # Check 3: Database integrity
    log_info "Check 3: Checking database integrity..."
    if sqlite3 "$DB_FILE" "PRAGMA integrity_check;" | grep -q "ok"; then
        log_info "Database integrity: OK"
    else
        log_error "Database integrity check failed"
        exit 1
    fi
    
    # Check 4: Create backup
    log_info "Check 4: Creating pre-migration backup..."
    local backup_result=$(backup_database)
    log_info "Pre-migration backup: $backup_result"
    
    # Check 5: Verify backup
    log_info "Check 5: Verifying backup..."
    verify_migration "$backup_result"
    
    log_info "All pre-migration checks passed!"
    log_info "Safe to proceed with migration"
}

# ============================================================================
# MAIN COMMAND HANDLER
# ============================================================================

main() {
    local command="${1:-}"
    
    case "$command" in
        backup)
            backup_database
            ;;
        rollback)
            if [ -z "${2:-}" ]; then
                log_error "Usage: $0 rollback <backup_file>"
                exit 1
            fi
            rollback_database "$2"
            ;;
        verify)
            if [ -z "${2:-}" ]; then
                verify_migration
            else
                verify_migration "$2"
            fi
            ;;
        pre-check)
            pre_migration_checks
            ;;
        *)
            cat << EOF
Migration Safety Script - Database Backup & Rollback

USAGE:
  $0 backup              Create timestamped backup
  $0 rollback <file>     Restore from backup file
  $0 verify [file]       Verify backup integrity (current DB if no file)
  $0 pre-check           Run all pre-migration checks

EXAMPLES:
  # Create backup before migration
  $0 backup

  # Rollback if migration fails
  $0 rollback backups/polyedge-20260420_224431.db

  # Verify backup
  $0 verify backups/polyedge-20260420_224431.db

  # Run pre-migration checks
  $0 pre-check

BACKUP LOCATION:
  $BACKUP_DIR/

DATABASE:
  $DB_FILE

EOF
            exit 1
            ;;
    esac
}

main "$@"
