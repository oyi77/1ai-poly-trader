import sqlite3
import os

db_files = [
    "./.omc/state/jobs.db",
    "./data/trading.db",
    "./data/polyedge.db",
    "./frontend/tradingbot.db",
    "./tradingbot.db",
    "./backend/data/polyedge.db",
    "./backend/trading.db",
    "./backend/tradingbot.db",
    "./backend/polyedge.db",
    "./backend/trading_bot.db",
]

for db_file in db_files:
    if not os.path.exists(db_file): continue
    print(f"--- {db_file} ---")
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_state'")
        if cursor.fetchone():
            cursor.execute("SELECT mode, bankroll, total_pnl, is_running FROM bot_state")
            rows = cursor.fetchall()
            for row in rows:
                print(f"  {row}")
        else:
            print("  No bot_state table")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")
