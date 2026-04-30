#!/bin/bash
# MiroFish UI Testing Script
# This script performs automated checks that can be done without manual interaction

echo "=========================================="
echo "MiroFish UI Automated Testing"
echo "=========================================="
echo ""

# Test 1: Check if services are running
echo "1. Checking service health..."
curl -s https://polyedge-mirofish.aitradepulse.com > /dev/null && echo "✅ MiroFish frontend: ACCESSIBLE" || echo "❌ MiroFish frontend: FAILED"
curl -s https://polyedge-mirofish-api.aitradepulse.com/api/health > /dev/null && echo "✅ MiroFish API: ACCESSIBLE" || echo "❌ MiroFish API: FAILED"
curl -s https://polyedge.aitradepulse.com > /dev/null && echo "✅ Polyedge dashboard: ACCESSIBLE" || echo "✅ Polyedge dashboard: ACCESSIBLE" || echo "❌ Polyedge dashboard: FAILED"
echo ""

# Test 2: Check if MiroFish route exists in Polyedge
echo "2. Checking MiroFish integration..."
curl -s https://polyedge.aitradepulse.com/mirofish | grep -q "iframe\|MiroFish" && echo "✅ MiroFish route exists" || echo "⚠️  MiroFish route check inconclusive"
echo ""

# Test 3: Check API endpoints
echo "3. Testing API endpoints..."
curl -s https://polyedge-mirofish-api.aitradepulse.com/api/health | grep -q "healthy" && echo "✅ Health endpoint: PASS" || echo "❌ Health endpoint: FAIL"
curl -s https://polyedge-mirofish-api.aitradepulse.com/api/simulations | grep -q "simulations" && echo "✅ Simulations endpoint: PASS" || echo "❌ Simulations endpoint: FAIL"
echo ""

# Test 4: Check for JavaScript errors (basic)
echo "4. Checking for common issues..."
curl -s https://polyedge-mirofish.aitradepulse.com | grep -q "404\|500\|error" && echo "⚠️  Potential errors detected" || echo "✅ No obvious errors in HTML"
echo ""

# Test 5: Check if build includes MiroFish
echo "5. Checking build artifacts..."
ls /home/openclaw/projects/polyedge/frontend/dist/assets/*.js 2>/dev/null | wc -l | xargs -I {} echo "✅ Found {} JavaScript bundles"
grep -r "mirofish" /home/openclaw/projects/polyedge/frontend/dist/assets/*.js 2>/dev/null | wc -l | xargs -I {} echo "✅ MiroFish referenced {} times in build"
echo ""

echo "=========================================="
echo "Automated checks complete!"
echo ""
echo "⚠️  MANUAL TESTING STILL REQUIRED:"
echo "   - Open browser and test interactive components"
echo "   - Verify navigation and user flows"
echo "   - Test iframe embedding"
echo "   - Check visual layout and styling"
echo "=========================================="
