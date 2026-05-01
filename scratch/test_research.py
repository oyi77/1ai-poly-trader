import asyncio
import logging
from backend.core.agi_jobs import research_pipeline_job
from backend.core.scheduler import log_event

# Mock log_event to avoid errors if scheduler not initialized
def mock_log_event(t, m, d=None):
    print(f"[{t.upper()}] {m}")

import backend.core.scheduler
backend.core.scheduler.log_event = mock_log_event

async def test():
    logging.basicConfig(level=logging.INFO)
    print("Starting research pipeline test...")
    await research_pipeline_job()
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(test())
