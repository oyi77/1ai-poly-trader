#!/bin/bash
# Test: Complete backup verification flow
# Creates a backup, verifies it passes all checks

set -e

TEST_DIR="/tmp/backup_verification_test_$$"
TEST_DB="$TEST_DIR/test.db"
TEST_BACKUP="$TEST_DIR/test_backup.db"
TEMP_RESTORE="$TEST_DIR/test_restore.db"
LOG_FILE="$TEST_DIR/test.log"

mkdir -p "$TEST_DIR"

log_test() {
    local msg=$1
    echo "[TEST] $msg" | tee -a "$LOG_FILE"
}

cleanup() {
    rm -rf "$TEST_DIR"
}

trap cleanup EXIT

log_test "========== BACKUP VERIFICATION TEST START =========="
log_test "Test directory: $TEST_DIR"

log_test "Step 1: Create test database with sample data"
sqlite3 "$TEST_DB" << 'EOF'
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    market_id TEXT,
    amount REAL,
    created_at TIMESTAMP
);

CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    strategy TEXT,
    confidence REAL,
    created_at TIMESTAMP
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    action TEXT,
    details TEXT,
    created_at TIMESTAMP
);

INSERT INTO trades (market_id, amount, created_at) VALUES 
    ('market_1', 100.0, datetime('now')),
    ('market_2', 250.5, datetime('now')),
    ('market_3', 75.25, datetime('now'));

INSERT INTO signals (strategy, confidence, created_at) VALUES 
    ('btc_momentum', 0.85, datetime('now')),
    ('weather_emos', 0.72, datetime('now'));

INSERT INTO audit_log (action, details, created_at) VALUES 
    ('backup_test', 'Test backup created', datetime('now'));
EOF

ORIGINAL_TRADES=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM trades;")
ORIGINAL_SIGNALS=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM signals;")
ORIGINAL_AUDIT=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM audit_log;")

log_test "✓ Test database created with $ORIGINAL_TRADES trades, $ORIGINAL_SIGNALS signals, $ORIGINAL_AUDIT audit logs"

log_test "Step 2: Create backup"
sqlite3 "$TEST_DB" ".backup '$TEST_BACKUP'"
BACKUP_SIZE=$(stat -c%s "$TEST_BACKUP" 2>/dev/null)
log_test "✓ Backup created: $BACKUP_SIZE bytes"

log_test "Step 3: Verify backup file integrity"
if ! sqlite3 "$TEST_BACKUP" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
    log_test "✗ FAILED: Backup integrity check failed"
    exit 1
fi
log_test "✓ Backup integrity check passed"

log_test "Step 4: Dry-run restore test"
cp "$TEST_BACKUP" "$TEMP_RESTORE"
TABLE_COUNT=$(sqlite3 "$TEMP_RESTORE" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
if [ "$TABLE_COUNT" -eq 0 ]; then
    log_test "✗ FAILED: No tables found in restored database"
    exit 1
fi
log_test "✓ Dry-run restore test passed - $TABLE_COUNT tables accessible"

log_test "Step 5: Verify schemas match"
ORIGINAL_SCHEMA=$(sqlite3 "$TEST_DB" "PRAGMA table_info(trades);")
BACKUP_SCHEMA=$(sqlite3 "$TEST_BACKUP" "PRAGMA table_info(trades);")
if [ "$ORIGINAL_SCHEMA" != "$BACKUP_SCHEMA" ]; then
    log_test "✗ FAILED: Schema mismatch in trades table"
    exit 1
fi
log_test "✓ Schema verification passed"

log_test "Step 6: Verify row counts match"
BACKUP_TRADES=$(sqlite3 "$TEST_BACKUP" "SELECT COUNT(*) FROM trades;")
BACKUP_SIGNALS=$(sqlite3 "$TEST_BACKUP" "SELECT COUNT(*) FROM signals;")
BACKUP_AUDIT=$(sqlite3 "$TEST_BACKUP" "SELECT COUNT(*) FROM audit_log;")

if [ "$ORIGINAL_TRADES" != "$BACKUP_TRADES" ]; then
    log_test "✗ FAILED: Trades row count mismatch (original: $ORIGINAL_TRADES, backup: $BACKUP_TRADES)"
    exit 1
fi

if [ "$ORIGINAL_SIGNALS" != "$BACKUP_SIGNALS" ]; then
    log_test "✗ FAILED: Signals row count mismatch (original: $ORIGINAL_SIGNALS, backup: $BACKUP_SIGNALS)"
    exit 1
fi

if [ "$ORIGINAL_AUDIT" != "$BACKUP_AUDIT" ]; then
    log_test "✗ FAILED: Audit log row count mismatch (original: $ORIGINAL_AUDIT, backup: $BACKUP_AUDIT)"
    exit 1
fi

log_test "✓ Row count verification passed"
log_test "  - trades: $BACKUP_TRADES rows"
log_test "  - signals: $BACKUP_SIGNALS rows"
log_test "  - audit_log: $BACKUP_AUDIT rows"

log_test "Step 7: Verify data integrity (sample query)"
BACKUP_TOTAL=$(sqlite3 "$TEST_BACKUP" "SELECT SUM(amount) FROM trades;")
ORIGINAL_TOTAL=$(sqlite3 "$TEST_DB" "SELECT SUM(amount) FROM trades;")
if [ "$BACKUP_TOTAL" != "$ORIGINAL_TOTAL" ]; then
    log_test "✗ FAILED: Data integrity check failed (sum mismatch)"
    exit 1
fi
log_test "✓ Data integrity verified (total amount: $BACKUP_TOTAL)"

log_test "========== BACKUP VERIFICATION TEST PASSED =========="
log_test "All verification checks completed successfully:"
log_test "  ✓ Backup file created and sized correctly"
log_test "  ✓ Backup integrity check passed"
log_test "  ✓ Dry-run restore test passed"
log_test "  ✓ Schema verification passed"
log_test "  ✓ Row count verification passed"
log_test "  ✓ Data integrity verified"

cat "$LOG_FILE"
exit 0
