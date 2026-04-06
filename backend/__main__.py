"""
PolyEdge entry point.

Run with:
    python -m backend

Starts the full orchestrator: weather scanner, copy trader, Telegram bot,
CLOB execution, and APScheduler jobs.
"""
import asyncio
import sys

from backend.core.orchestrator import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
