# MiroFish Complete Deployment & Testing Guide

**Date**: 2026-04-21 14:12 UTC
**Status**: 🚧 IN PROGRESS - DEPLOYMENT REQUIRED

---

## Current Status

### ✅ What's Done
- [x] MiroFish repository cloned to `/home/openclaw/projects/mirofish`
- [x] CF-router entries added (disabled) for polyedge-mirofish and polyedge-mirofish-api
- [x] Polyedge frontend: MiroFish page created with iframe embed
- [x] Polyedge frontend: Navigation link added
- [x] Polyedge backend: Client endpoint updated to polyedge-mirofish-api.aitradepulse.com
- [x] All code changes committed

### ❌ What's NOT Working Yet
- [ ] MiroFish service NOT running (requires Python 3.10/3.11, we have 3.13)
- [ ] CF-router entries disabled (enabled: false)
- [ ] Cannot test MiroFish independently
- [ ] Cannot test MiroFish integration from Polyedge
- [ ] No real-time debate streaming

---

## Deployment Options

### Option 1: Use Docker (RECOMMENDED)
**Pros**: Isolated environment, correct Python version
**Cons**: Docker not currently running

**Steps**:
1. Start Docker daemon
2. Pull MiroFish image: `docker pull ghcr.io/666ghj/mirofish:latest`
3. Configure .env file
4. Run: `docker-compose up -d`
5. Verify ports 3000 (UI) and 5001 (API) are accessible

### Option 2: Use pyenv to install Python 3.11
**Pros**: Native installation, better performance
**Cons**: Requires pyenv setup

**Steps**:
1. Install pyenv if not present
2. Install Python 3.11: `pyenv install 3.11`
3. Create venv with Python 3.11
4. Install dependencies
5. Run MiroFish backend and frontend

### Option 3: Deploy to separate server
**Pros**: Production-ready, isolated
**Cons**: Requires server access

---

## Testing Checklist

### Phase 1: MiroFish Standalone Testing
- [ ] MiroFish UI accessible at http://localhost:3000
- [ ] MiroFish API accessible at http://localhost:5001
- [ ] Can create a new simulation
- [ ] Agents spawn and start debating
- [ ] Knowledge graph builds
- [ ] Prediction report generates

### Phase 2: CF-Router Integration
- [ ] Enable polyedge-mirofish in CF-router apps.yaml
- [ ] Enable polyedge-mirofish-api in CF-router apps.yaml
- [ ] Reload CF-router: `pm2 restart cf-router`
- [ ] Test https://polyedge-mirofish.aitradepulse.com loads UI
- [ ] Test https://polyedge-mirofish-api.aitradepulse.com/api/health responds

### Phase 3: Polyedge Integration Testing
- [ ] Navigate to https://polyedge.aitradepulse.com/mirofish
- [ ] Iframe loads MiroFish UI successfully
- [ ] "Open Full UI" button works
- [ ] Enable MiroFish in Polyedge Settings
- [ ] Test connection button succeeds
- [ ] Generate trading signal
- [ ] Verify debate routes to MiroFish
- [ ] Check debate result appears in Polyedge

### Phase 4: E2E Flow Testing
- [ ] Create market prediction in MiroFish
- [ ] Agents debate and reach consensus
- [ ] Prediction appears in Polyedge dashboard
- [ ] Trading signal generated based on MiroFish prediction
- [ ] Order placed (paper trading)
- [ ] Result tracked in decision log

---

## Immediate Next Steps

### Step 1: Get MiroFish Running
**Choose deployment method and execute**

**Docker Method** (if Docker available):
```bash
cd /home/openclaw/projects/mirofish
# Check if Docker is running
docker ps

# If not, start Docker
sudo systemctl start docker

# Pull and run MiroFish
docker-compose up -d

# Check logs
docker-compose logs -f
```

**Python 3.11 Method** (if pyenv available):
```bash
cd /home/openclaw/projects/mirofish

# Install Python 3.11
pyenv install 3.11.0
pyenv local 3.11.0

# Create venv
python -m venv venv
source venv/bin/activate

# Install dependencies
cd backend
pip install -r requirements.txt

# Run backend
python run.py &

# Run frontend (in another terminal)
cd ../frontend
npm install
npm run dev
```

### Step 2: Verify MiroFish Works Standalone
```bash
# Test UI
curl http://localhost:3000

# Test API
curl http://localhost:5001/api/health

# Open browser
xdg-open http://localhost:3000
```

### Step 3: Enable CF-Router
```bash
cd ~/.cloudflare-router

# Edit apps.yaml - change enabled: false to enabled: true
# For both polyedge-mirofish and polyedge-mirofish-api

# Reload CF-router
pm2 restart cf-router

# Test
curl https://polyedge-mirofish.aitradepulse.com
curl https://polyedge-mirofish-api.aitradepulse.com/api/health
```

### Step 4: Test Polyedge Integration
```bash
# Open Polyedge
xdg-open https://polyedge.aitradepulse.com/mirofish

# Should see MiroFish UI embedded
# Should be able to interact with agents
```

---

## Configuration Files

### MiroFish .env (already created)
```bash
# Location: /home/openclaw/projects/mirofish/.env
LLM_API_KEY=sk-ant-api03-placeholder
LLM_BASE_URL=https://ai.aitradepulse.com/v1
LLM_MODEL_NAME=claude-3-5-sonnet-20241022
```

### CF-Router apps.yaml (entries added, need to enable)
```yaml
# Location: ~/.cloudflare-router/apps.yaml
polyedge-mirofish:
  mode: port
  enabled: false  # ← Change to true
  hostname: polyedge-mirofish.aitradepulse.com
  port: 3000
  health_check: /

polyedge-mirofish-api:
  mode: port
  enabled: false  # ← Change to true
  hostname: polyedge-mirofish-api.aitradepulse.com
  port: 5001
  health_check: /api/health
```

---

## Troubleshooting

### MiroFish won't start
- Check Python version: `python --version` (needs 3.10 or 3.11)
- Check dependencies: `pip list | grep camel`
- Check logs: `docker-compose logs` or `tail -f backend/logs/*.log`

### CF-Router not routing
- Check CF-router status: `pm2 status cf-router`
- Check CF-router logs: `pm2 logs cf-router`
- Verify ports are listening: `netstat -tlnp | grep -E '3000|5001'`

### Polyedge iframe not loading
- Check browser console for CORS errors
- Verify MiroFish is accessible: `curl https://polyedge-mirofish.aitradepulse.com`
- Check iframe sandbox attributes

### Debate not routing to MiroFish
- Check MiroFish enabled in Settings
- Verify API endpoint: `curl https://polyedge-mirofish-api.aitradepulse.com/api/health`
- Check backend logs: `tail -f backend/logs/app.log`

---

## Success Criteria

✅ MiroFish UI loads at https://polyedge-mirofish.aitradepulse.com
✅ MiroFish API responds at https://polyedge-mirofish-api.aitradepulse.com
✅ Can create simulation and see agents debating
✅ Polyedge /mirofish page loads with embedded UI
✅ Can enable MiroFish in Polyedge settings
✅ Trading signals route to MiroFish for debate
✅ Debate results appear in Polyedge dashboard

---

## Current Blocker

**Python Version Mismatch**
- System has Python 3.13
- MiroFish requires Python 3.10 or 3.11
- camel-oasis package not compatible with 3.13

**Solutions**:
1. Use Docker (isolates Python version)
2. Use pyenv to install Python 3.11
3. Deploy to separate server with correct Python version

**Recommended**: Use Docker for quickest deployment
