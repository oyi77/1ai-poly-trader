"""
Add CHECK constraints for enum-like String columns

Values derived from validate_schema_constraints.py audit (Task 1).
Uses raw SQL for SQLite compatibility to avoid batch_alter_table temp table issues.

Revision ID: 20260504_add_enum_check_constraints
Revises: 20260504_add_strategy_fk_constraints
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa

revision = '20260504_add_enum_check_constraints'
down_revision = '20260504_add_strategy_fk_constraints'
branch_labels = None
depends_on = None

CHECKS = {
    "trades": {
        "ck_trades_direction": ("direction", ["up", "down", "yes", "no"]),
        "ck_trades_source": ("source", ["bot", "import", "manual", "external", "import_frontend", "orphaned"]),
    },
    "signals": {
        "ck_signals_direction": ("direction", ["up", "down"]),
    },
    "strategy_outcomes": {
        "ck_strat_outcomes_direction": ("direction", ["up", "down", "yes", "no", "unknown"]),
    },
    "trade_attempts": {
        "ck_trade_attempts_direction": ("direction", ["up", "down", "yes", "no", "buy", "sell"]),
        "ck_trade_attempts_status": ("status", [
            "STARTED", "PREFLIGHT", "RISK_GATE", "SIZING", "CONTEXT",
            "EXECUTED", "REJECTED", "FAILED", "BLOCKED",
        ]),
        "ck_trade_attempts_phase": ("phase", [
            "created", "preflight", "risk_gate", "sizing", "context",
            "execution", "validation", "completed",
        ]),
    },
    "copy_trader_entries": {
        "ck_copy_trader_entries_side": ("side", ["YES", "NO"]),
    },
    "whale_transactions": {
        "ck_whale_tx_side": ("side", ["buy", "sell"]),
    },
    "strategy_config": {
        "ck_strat_config_trading_mode": ("trading_mode", ["paper", "testnet", "live"]),
    },
    "experiment_records": {
        "ck_exp_records_status": ("status", [
            "candidate", "draft", "shadow", "paper", "live_trial",
            "live_promoted", "retired", "active",
        ]),
    },
    "job_queue": {
        "ck_job_queue_status": ("status", ["pending", "processing", "completed", "failed"]),
    },
    "pending_approvals": {
        "ck_pending_approvals_status": ("status", ["pending", "approved", "rejected"]),
    },
    "strategy_health": {
        "ck_strategy_health_status": ("status", [
            "active", "degraded", "disabled", "killed", "warned",
        ]),
    },
    "strategy_proposal": {
        "ck_strat_proposal_admin_decision": ("admin_decision", ["pending", "approved", "rejected"]),
    },
    "decision_log": {
        "ck_decision_log_decision": ("decision", [
            "BUY", "SKIP", "SELL", "HOLD", "ERROR", "FOLLOW",
        ]),
    },
}


def _build_check_expr(column, valid_values):
    quoted = ", ".join(f"'{v}'" for v in valid_values)
    return f"({column} IS NULL OR {column} IN ({quoted}))"


def upgrade() -> None:
    conn = op.get_bind()
    raw = conn.connection.dbapi_connection

    conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
    raw.execute("PRAGMA foreign_keys=OFF")

    conn.commit()

    for name in raw.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_alembic_tmp%'"
    ).fetchall():
        raw.execute('DROP TABLE IF EXISTS [' + name[0] + ']')

    existing = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    for table, constraints in CHECKS.items():
        if table not in existing or not constraints:
            continue

        orig_ddl = raw.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
        ).fetchone()
        if orig_ddl:
            existing_cks = {ck for ck in constraints if f'CONSTRAINT [{ck}]' in orig_ddl[0]}
            if len(existing_cks) == len(constraints):
                continue

        col_defs = raw.execute(f"PRAGMA table_info([{table}])").fetchall()
        fk_defs = raw.execute(f"PRAGMA foreign_key_list([{table}])").fetchall()

        col_sqls = []
        for cid, cname, ctype, notnull, dflt, pk in col_defs:
            parts = [f"[{cname}]", ctype]
            if pk:
                parts.append("NOT NULL")
            elif notnull:
                parts.append("NOT NULL")
            if dflt is not None:
                parts.append(f"DEFAULT {dflt}")
            col_sqls.append(" ".join(parts))

        pk_cols = [r[1] for r in col_defs if r[5] == 1]
        if pk_cols:
            col_sqls.append(f"PRIMARY KEY ({', '.join(f'[{c}]' for c in pk_cols)})")

        for fk_id, seq, ref_table, from_col, to_col, on_update, on_delete, _match in fk_defs:
            col_sqls.append(
                f"FOREIGN KEY([{from_col}]) REFERENCES [{ref_table}] ([{to_col}])"
                f" ON DELETE {on_delete or 'NO ACTION'} ON UPDATE {on_update or 'NO ACTION'}"
            )

        for ck_name, (column, valid) in constraints.items():
            col_sqls.append(f"CONSTRAINT [{ck_name}] CHECK {_build_check_expr(column, valid)}")

        col_list = ", ".join(f"[{r[1]}]" for r in col_defs)
        tmp = f"_alembic_tmp_{table}"

        raw.execute(f"CREATE TABLE [{tmp}] ({', '.join(col_sqls)})")
        raw.execute(f"INSERT INTO [{tmp}] ({col_list}) SELECT {col_list} FROM [{table}]")
        raw.execute(f"DROP TABLE [{table}]")
        raw.execute(f"ALTER TABLE [{tmp}] RENAME TO [{table}]")

    raw.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("PRAGMA foreign_keys=OFF"))

    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())

    for table, constraints in CHECKS.items():
        if table not in existing or not constraints:
            continue

        col_defs = conn.execute(sa.text(f"PRAGMA table_info([{table}])")).fetchall()
        fk_defs = conn.execute(sa.text(f"PRAGMA foreign_key_list([{table}])")).fetchall()

        col_sqls = []
        for cid, cname, ctype, notnull, dflt, pk in col_defs:
            parts = [f"[{cname}]", ctype]
            if pk:
                parts.append("NOT NULL")
            elif notnull:
                parts.append("NOT NULL")
            if dflt is not None:
                parts.append(f"DEFAULT {dflt}")
            col_sqls.append(" ".join(parts))

        pk_cols = [r[1] for r in col_defs if r[5] == 1]
        if pk_cols:
            col_sqls.append(f"PRIMARY KEY ({', '.join(f'[{c}]' for c in pk_cols)})")

        for fk_id, seq, ref_table, from_col, to_col, on_update, on_delete, _match in fk_defs:
            col_sqls.append(
                f"FOREIGN KEY([{from_col}]) REFERENCES [{ref_table}] ([{to_col}])"
                f" ON DELETE {on_delete or 'NO ACTION'} ON UPDATE {on_update or 'NO ACTION'}"
            )

        check_names_to_drop = set(constraints.keys())
        existing_checks = conn.execute(sa.text(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
        )).scalar()
        for ck_name in check_names_to_drop:
            if existing_checks and f"CONSTRAINT [{ck_name}]" in existing_checks:
                pass

        col_list = ", ".join(f"[{r[1]}]" for r in col_defs)
        tmp = f"_alembic_tmp_{table}"

        ddl = f"CREATE TABLE [{tmp}] ({', '.join(col_sqls)})"
        conn.execute(sa.text(ddl))
        conn.execute(sa.text(
            f"INSERT INTO [{tmp}] ({col_list}) SELECT {col_list} FROM [{table}]"
        ))
        conn.execute(sa.text(f"DROP TABLE [{table}]"))
        conn.execute(sa.text(f"ALTER TABLE [{tmp}] RENAME TO [{table}]"))

    conn.execute(sa.text("PRAGMA foreign_keys=ON"))
