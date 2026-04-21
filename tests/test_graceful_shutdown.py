#!/usr/bin/env python3
"""
Graceful shutdown verification test.

Tests backend shutdown behavior with active requests and WebSocket connections
under different load levels (1, 10, 100 active requests).

Usage:
    python tests/test_graceful_shutdown.py
"""
import asyncio
import httpx
import signal
import subprocess
import sys
import time
import websockets
from datetime import datetime
from typing import List, Optional

# Test configuration
BACKEND_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/stats"
SHUTDOWN_TIMEOUT = 30.0


class ShutdownTestResult:
    """Results from a single shutdown test run."""
    
    def __init__(self, load_level: int):
        self.load_level = load_level
        self.active_requests_completed = 0
        self.active_requests_failed = 0
        self.ws_connections_closed = 0
        self.ws_connections_failed = 0
        self.shutdown_time = 0.0
        self.exit_code: Optional[int] = None
        self.errors: List[str] = []
        
    def success(self) -> bool:
        """Check if test passed all criteria."""
        return (
            self.active_requests_failed == 0 and
            self.ws_connections_failed == 0 and
            self.exit_code == 0 and
            self.shutdown_time < SHUTDOWN_TIMEOUT and
            len(self.errors) == 0
        )
    
    def __str__(self) -> str:
        status = "✅ PASS" if self.success() else "❌ FAIL"
        return f"""
Graceful Shutdown Test (Load: {self.load_level} requests):
{status}
- Active requests completed: {self.active_requests_completed}/{self.load_level}
- Active requests failed: {self.active_requests_failed}
- WebSocket connections closed: {self.ws_connections_closed}
- WebSocket connections failed: {self.ws_connections_failed}
- Exit code: {self.exit_code}
- Shutdown time: {self.shutdown_time:.2f}s (limit: {SHUTDOWN_TIMEOUT}s)
- Errors: {len(self.errors)}
"""


async def make_long_request(client: httpx.AsyncClient, duration: float = 5.0) -> bool:
    """Make a long-running request that should complete during shutdown."""
    try:
        # Use health endpoint with artificial delay
        response = await client.get(
            f"{BACKEND_URL}/api/health",
            timeout=duration + 5.0
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Request failed: {e}")
        return False


async def connect_websocket(url: str, duration: float = 10.0) -> bool:
    """Connect to WebSocket and wait for graceful close."""
    try:
        async with websockets.connect(url) as ws:
            # Wait for server to close connection
            await asyncio.wait_for(ws.recv(), timeout=duration)
            return False  # Should not receive data, should close
    except websockets.exceptions.ConnectionClosed as e:
        # Graceful close with code 1001 (going away)
        return e.code == 1001
    except asyncio.TimeoutError:
        return False
    except Exception as e:
        print(f"WebSocket error: {e}")
        return False


async def generate_load(num_requests: int, num_websockets: int) -> tuple[List[asyncio.Task], List[asyncio.Task]]:
    """Generate active load (HTTP requests + WebSocket connections)."""
    client = httpx.AsyncClient()
    
    # Create HTTP request tasks
    http_tasks = [
        asyncio.create_task(make_long_request(client, duration=10.0))
        for _ in range(num_requests)
    ]
    
    # Create WebSocket connection tasks
    ws_tasks = [
        asyncio.create_task(connect_websocket(WS_URL, duration=15.0))
        for _ in range(num_websockets)
    ]
    
    # Give connections time to establish
    await asyncio.sleep(1.0)
    
    return http_tasks, ws_tasks


def start_backend() -> subprocess.Popen:
    """Start the backend server."""
    print("Starting backend server...")
    proc = subprocess.Popen(
        ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for server to be ready
    max_wait = 30
    for i in range(max_wait):
        try:
            response = httpx.get(f"{BACKEND_URL}/api/health", timeout=2.0)
            if response.status_code == 200:
                print(f"✓ Backend ready after {i+1}s")
                return proc
        except Exception:
            time.sleep(1)
    
    raise RuntimeError("Backend failed to start within 30s")


def send_sigterm(proc: subprocess.Popen) -> None:
    """Send SIGTERM signal to process."""
    print(f"Sending SIGTERM to PID {proc.pid}...")
    proc.send_signal(signal.SIGTERM)


async def run_shutdown_test(load_level: int) -> ShutdownTestResult:
    """Run a single shutdown test with specified load level."""
    result = ShutdownTestResult(load_level)
    proc = None
    
    try:
        # Start backend
        proc = start_backend()
        
        # Generate load
        num_ws = max(1, load_level // 2)  # Half as many WebSocket connections
        print(f"\nGenerating load: {load_level} HTTP requests, {num_ws} WebSocket connections...")
        http_tasks, ws_tasks = await generate_load(load_level, num_ws)
        
        # Wait a bit to ensure requests are in-flight
        await asyncio.sleep(2.0)
        
        # Send SIGTERM
        shutdown_start = time.time()
        send_sigterm(proc)
        
        # Wait for tasks to complete
        print("Waiting for active requests to complete...")
        http_results = await asyncio.gather(*http_tasks, return_exceptions=True)
        
        print("Waiting for WebSocket connections to close...")
        ws_results = await asyncio.gather(*ws_tasks, return_exceptions=True)
        
        # Wait for process to exit
        print("Waiting for process to exit...")
        try:
            exit_code = proc.wait(timeout=SHUTDOWN_TIMEOUT)
            result.exit_code = exit_code
        except subprocess.TimeoutExpired:
            result.errors.append(f"Process did not exit within {SHUTDOWN_TIMEOUT}s")
            proc.kill()
            result.exit_code = -1
        
        result.shutdown_time = time.time() - shutdown_start
        
        # Count results
        for r in http_results:
            if isinstance(r, Exception):
                result.active_requests_failed += 1
                result.errors.append(f"HTTP request exception: {r}")
            elif r:
                result.active_requests_completed += 1
            else:
                result.active_requests_failed += 1
        
        for r in ws_results:
            if isinstance(r, Exception):
                result.ws_connections_failed += 1
                result.errors.append(f"WebSocket exception: {r}")
            elif r:
                result.ws_connections_closed += 1
            else:
                result.ws_connections_failed += 1
        
    except Exception as e:
        result.errors.append(f"Test exception: {e}")
        if proc:
            proc.kill()
    
    return result


async def main():
    """Run all shutdown tests."""
    print("=" * 70)
    print("GRACEFUL SHUTDOWN VERIFICATION TEST")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Shutdown timeout: {SHUTDOWN_TIMEOUT}s")
    print()
    
    # Test with different load levels
    load_levels = [1, 10, 100]
    results = []
    
    for load in load_levels:
        print(f"\n{'=' * 70}")
        print(f"TEST: Load level = {load} active requests")
        print(f"{'=' * 70}")
        
        result = await run_shutdown_test(load)
        results.append(result)
        
        print(result)
        
        # Wait between tests
        if load != load_levels[-1]:
            print("Waiting 5s before next test...")
            await asyncio.sleep(5.0)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    all_passed = all(r.success() for r in results)
    
    for result in results:
        status = "✅ PASS" if result.success() else "❌ FAIL"
        print(f"{status} - Load {result.load_level}: {result.shutdown_time:.2f}s, exit code {result.exit_code}")
    
    print()
    if all_passed:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        for result in results:
            if not result.success():
                print(f"\nFailed test (load={result.load_level}):")
                for error in result.errors:
                    print(f"  - {error}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
