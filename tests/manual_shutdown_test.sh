#!/bin/bash
# Manual graceful shutdown test
# Tests backend shutdown with active load

set -e

BACKEND_PORT=8200
BACKEND_URL="http://localhost:${BACKEND_PORT}"
LOG_FILE="/tmp/shutdown_test_$(date +%s).log"

echo "======================================================================="
echo "GRACEFUL SHUTDOWN VERIFICATION TEST"
echo "======================================================================="
echo "Backend URL: ${BACKEND_URL}"
echo "Log file: ${LOG_FILE}"
echo ""

# Start backend
echo "1. Starting backend server on port ${BACKEND_PORT}..."
cd /home/openclaw/projects/polyedge
uvicorn backend.api.main:app --host 0.0.0.0 --port ${BACKEND_PORT} > "${LOG_FILE}" 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: ${BACKEND_PID}"

# Wait for backend to be ready
echo "2. Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s "${BACKEND_URL}/api/health" > /dev/null 2>&1; then
        echo "   ✓ Backend ready after ${i}s"
        break
    fi
    sleep 1
done

# Generate load
echo "3. Generating load (10 concurrent requests)..."
for i in {1..10}; do
    curl -s "${BACKEND_URL}/api/health" > /dev/null 2>&1 &
done
echo "   ✓ 10 requests started"

# Wait a bit for requests to be in-flight
sleep 2

# Send SIGTERM
echo "4. Sending SIGTERM to backend (PID ${BACKEND_PID})..."
SHUTDOWN_START=$(date +%s)
kill -TERM ${BACKEND_PID}

# Wait for process to exit
echo "5. Waiting for graceful shutdown..."
if wait ${BACKEND_PID} 2>/dev/null; then
    EXIT_CODE=$?
else
    EXIT_CODE=$?
fi

SHUTDOWN_END=$(date +%s)
SHUTDOWN_TIME=$((SHUTDOWN_END - SHUTDOWN_START))

echo ""
echo "======================================================================="
echo "RESULTS"
echo "======================================================================="
echo "Exit code: ${EXIT_CODE}"
echo "Shutdown time: ${SHUTDOWN_TIME}s"
echo ""

# Check log for shutdown sequence
echo "Shutdown sequence from log:"
grep -E "(GRACEFUL SHUTDOWN|Shutting down|shut down|cancelled|closed|Exit code)" "${LOG_FILE}" | tail -20

echo ""
if [ ${EXIT_CODE} -eq 0 ] && [ ${SHUTDOWN_TIME} -lt 30 ]; then
    echo "✅ TEST PASSED"
    echo "   - Exit code: 0"
    echo "   - Shutdown time: ${SHUTDOWN_TIME}s < 30s"
    exit 0
else
    echo "❌ TEST FAILED"
    [ ${EXIT_CODE} -ne 0 ] && echo "   - Exit code: ${EXIT_CODE} (expected 0)"
    [ ${SHUTDOWN_TIME} -ge 30 ] && echo "   - Shutdown time: ${SHUTDOWN_TIME}s >= 30s"
    exit 1
fi
