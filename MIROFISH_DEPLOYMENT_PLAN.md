# MiroFish Deployment & Integration Plan

**Date**: 2026-04-21  
**Status**: 🚧 IN PROGRESS

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    User Browser                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  polyedge.aitradepulse.com                                   │
│  ├─ Dashboard (existing)                                     │
│  ├─ BrainGraph (Bull/Bear/Judge visualization)              │
│  ├─ Settings (MiroFish toggle + credentials)                │
│  └─ MiroFish Tab (NEW - iframe to MiroFish UI)              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                          │
                          ├──────────────────┐
                          │                  │
                          ▼                  ▼
┌──────────────────────────────┐  ┌──────────────────────────┐
│  ai.aitradepulse.com         │  │ polyedge-mirofish        │
│  (OmniRoute AI Router)       │  │ .aitradepulse.com        │
│                              │  │ (MiroFish Standalone UI) │
│  Routes to:                  │  │                          │
│  - Claude                    │  │  - Agent Simulation      │
│  - GPT-4                     │  │  - Knowledge Graph       │
│  - Groq                      │  │  - Debate Visualization  │
│  - MiroFish API              │  │  - Prediction Reports    │
└──────────────────────────────┘  └──────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  MiroFish Backend API                                         │
│  (Self-hosted or cloud)                                       │
│                                                               │
│  Endpoints:                                                   │
│  - POST /api/signals (get debate signals)                    │
│  - GET /api/agents (list active agents)                      │
│  - GET /api/simulations (list simulations)                   │
│  - POST /api/simulate (start new simulation)                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Current Status

### ✅ Already Implemented
- [x] MiroFish client in backend (`backend/ai/mirofish_client.py`)
- [x] Debate router with fallback (`backend/ai/debate_router.py`)
- [x] Settings API for credentials (`backend/api/settings.py`)
- [x] Settings UI with toggle (`frontend/src/pages/Settings.tsx`)
- [x] BrainGraph with Bull/Bear/Judge visualization
- [x] Debate monitor tab in Admin panel
- [x] 129 tests passing

### 🚧 Missing Components
- [ ] MiroFish deployment at `polyedge-mirofish.aitradepulse.com`
- [ ] OmniRoute integration at `ai.aitradepulse.com`
- [ ] MiroFish UI embed in Polyedge
- [ ] Real-time debate streaming from MiroFish
- [ ] Agent activity visualization from MiroFish

---

## Implementation Tasks

### Phase 1: MiroFish Deployment (Infrastructure)

#### Task 1.1: Deploy MiroFish Service
**Location**: `polyedge-mirofish.aitradepulse.com`

**Steps**:
1. Clone MiroFish repo: `git clone https://github.com/666ghj/MiroFish.git`
2. Set up Docker Compose:
   ```yaml
   version: '3.8'
   services:
     mirofish-backend:
       build: ./backend
       ports:
         - "8000:8000"
       environment:
         - OPENAI_API_KEY=${OPENAI_API_KEY}
         - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
       
     mirofish-frontend:
       build: ./frontend
       ports:
         - "3000:3000"
       environment:
         - VITE_API_URL=https://polyedge-mirofish.aitradepulse.com/api
   ```
3. Configure nginx reverse proxy
4. Set up SSL certificates
5. Deploy to server

**Deliverables**:
- MiroFish UI accessible at `https://polyedge-mirofish.aitradepulse.com`
- MiroFish API accessible at `https://polyedge-mirofish.aitradepulse.com/api`

---

#### Task 1.2: Configure OmniRoute Integration
**Location**: `ai.aitradepulse.com`

**Steps**:
1. Add MiroFish as a provider in OmniRoute config:
   ```json
   {
     "providers": [
       {
         "name": "mirofish",
         "type": "custom",
         "endpoint": "https://polyedge-mirofish.aitradepulse.com/api",
         "auth": "bearer",
         "capabilities": ["debate", "simulation", "prediction"]
       }
     ]
   }
   ```
2. Test routing: `ai.aitradepulse.com/v1/mirofish/signals`
3. Set up API key authentication
4. Configure rate limiting

**Deliverables**:
- OmniRoute can route requests to MiroFish
- API endpoint: `https://ai.aitradepulse.com/v1/mirofish/*`

---

### Phase 2: Polyedge Integration (Frontend)

#### Task 2.1: Update MiroFish Client to Use OmniRoute
**File**: `backend/ai/mirofish_client.py`

**Changes**:
```python
# OLD
self.api_url = api_url or "https://api.mirofish.ai"

# NEW
self.api_url = api_url or "https://ai.aitradepulse.com/v1/mirofish"
```

**Test**:
```bash
curl -X POST https://ai.aitradepulse.com/v1/mirofish/signals \
  -H "Authorization: Bearer $MIROFISH_API_KEY" \
  -d '{"question": "Will BTC reach 100K?", "market_price": 0.5}'
```

---

#### Task 2.2: Add MiroFish Tab to Polyedge UI
**File**: `frontend/src/pages/MiroFish.tsx` (NEW)

**Implementation**:
```tsx
import { useState } from 'react'
import { ExternalLink } from 'lucide-react'

export default function MiroFish() {
  const [showExternal, setShowExternal] = useState(false)
  
  return (
    <div className="h-screen flex flex-col">
      <div className="p-4 border-b border-neutral-800 flex justify-between items-center">
        <h1 className="text-2xl font-bold">MiroFish Simulation</h1>
        <button
          onClick={() => window.open('https://polyedge-mirofish.aitradepulse.com', '_blank')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-700"
        >
          <ExternalLink className="w-4 h-4" />
          Open Full UI
        </button>
      </div>
      
      <iframe
        src="https://polyedge-mirofish.aitradepulse.com"
        className="flex-1 w-full border-0"
        title="MiroFish Simulation"
      />
    </div>
  )
}
```

**Add to Router**:
```tsx
// frontend/src/App.tsx
import MiroFish from './pages/MiroFish'

<Route path="/mirofish" element={<MiroFish />} />
```

**Add to Navigation**:
```tsx
// frontend/src/components/Sidebar.tsx
<NavLink to="/mirofish" icon={<Brain />}>
  MiroFish
</NavLink>
```

---

#### Task 2.3: Real-Time Debate Streaming
**File**: `frontend/src/components/DebateStream.tsx` (NEW)

**Implementation**:
```tsx
import { useEffect, useState } from 'react'
import { MessageSquare, TrendingUp, TrendingDown } from 'lucide-react'

interface DebateMessage {
  agent: 'bull' | 'bear' | 'judge'
  message: string
  timestamp: string
}

export default function DebateStream({ marketId }: { marketId: string }) {
  const [messages, setMessages] = useState<DebateMessage[]>([])
  
  useEffect(() => {
    const ws = new WebSocket('wss://ai.aitradepulse.com/v1/mirofish/stream')
    
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      setMessages(prev => [...prev, msg])
    }
    
    return () => ws.close()
  }, [marketId])
  
  return (
    <div className="space-y-4">
      {messages.map((msg, i) => (
        <div key={i} className="flex gap-3 p-4 bg-neutral-900 rounded-lg">
          {msg.agent === 'bull' && <TrendingUp className="w-5 h-5 text-green-500" />}
          {msg.agent === 'bear' && <TrendingDown className="w-5 h-5 text-red-500" />}
          {msg.agent === 'judge' && <MessageSquare className="w-5 h-5 text-blue-500" />}
          
          <div className="flex-1">
            <div className="flex justify-between items-center mb-2">
              <span className="font-semibold capitalize">{msg.agent}</span>
              <span className="text-xs text-neutral-500">{msg.timestamp}</span>
            </div>
            <p className="text-sm text-neutral-300">{msg.message}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
```

---

#### Task 2.4: Update BrainGraph to Show MiroFish Status
**File**: `frontend/src/components/BrainGraph.tsx`

**Changes**:
```tsx
// Add MiroFish connection status
const [mirofishStatus, setMirofishStatus] = useState<'connected' | 'disconnected'>('disconnected')

useEffect(() => {
  fetch('/api/v1/settings')
    .then(res => res.json())
    .then(data => {
      if (data.mirofish_enabled) {
        setMirofishStatus('connected')
      }
    })
}, [])

// Update MiroFish node
{ 
  id: 'mirofish', 
  type: 'custom', 
  position: { x: 400, y: 50 }, 
  data: { 
    label: 'MiroFish', 
    type: 'ai', 
    status: mirofishStatus === 'connected' ? 'active' : 'idle'
  } 
}
```

---

### Phase 3: Testing & Verification

#### Task 3.1: E2E Flow Test
**Test Scenario**: Complete trading flow with MiroFish

1. Enable MiroFish in Settings
2. Enter credentials for `ai.aitradepulse.com`
3. Test connection (should succeed)
4. Generate trading signal
5. Verify debate routes to MiroFish
6. Check debate visualization shows MiroFish agents
7. Verify fallback to local if MiroFish fails

**Expected Result**: ✅ All flows work

---

#### Task 3.2: UI Integration Test
**Test Scenario**: MiroFish UI embed

1. Navigate to `/mirofish` in Polyedge
2. Verify iframe loads MiroFish UI
3. Click "Open Full UI" button
4. Verify opens in new tab
5. Test agent interactions in MiroFish UI
6. Verify predictions appear in Polyedge

**Expected Result**: ✅ Seamless integration

---

## Configuration Files

### Environment Variables

**Polyedge Backend** (`.env`):
```bash
# MiroFish Integration
MIROFISH_ENABLED=true
MIROFISH_API_URL=https://ai.aitradepulse.com/v1/mirofish
MIROFISH_API_KEY=your-api-key-here
MIROFISH_API_TIMEOUT=30

# OmniRoute
OMNIROUTE_URL=https://ai.aitradepulse.com
OMNIROUTE_API_KEY=your-omniroute-key
```

**MiroFish Service** (`.env`):
```bash
# LLM Providers
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
GROQ_API_KEY=your-groq-key

# Database
POSTGRES_URL=postgresql://user:pass@localhost:5432/mirofish

# Redis (for agent memory)
REDIS_URL=redis://localhost:6379

# API
API_PORT=8000
CORS_ORIGINS=https://polyedge.aitradepulse.com,https://ai.aitradepulse.com
```

---

## Deployment Checklist

### Infrastructure
- [ ] MiroFish deployed at `polyedge-mirofish.aitradepulse.com`
- [ ] SSL certificates configured
- [ ] Nginx reverse proxy configured
- [ ] Docker containers running
- [ ] Health checks passing

### OmniRoute
- [ ] MiroFish provider added to OmniRoute
- [ ] API routing working: `ai.aitradepulse.com/v1/mirofish/*`
- [ ] Authentication configured
- [ ] Rate limiting configured

### Polyedge Backend
- [ ] MiroFish client updated to use OmniRoute
- [ ] Debate router tested with MiroFish
- [ ] Fallback logic verified
- [ ] All tests passing

### Polyedge Frontend
- [ ] MiroFish tab added to navigation
- [ ] Iframe embed working
- [ ] Real-time debate streaming implemented
- [ ] BrainGraph shows MiroFish status
- [ ] Settings UI updated

### Testing
- [ ] E2E flow test passed
- [ ] UI integration test passed
- [ ] Performance test passed
- [ ] Security audit passed

---

## Timeline

**Phase 1 (Infrastructure)**: 2-3 days
- Deploy MiroFish service
- Configure OmniRoute

**Phase 2 (Integration)**: 1-2 days
- Update Polyedge backend
- Add frontend components

**Phase 3 (Testing)**: 1 day
- E2E testing
- Bug fixes

**Total**: 4-6 days

---

## Success Criteria

✅ MiroFish UI accessible at `polyedge-mirofish.aitradepulse.com`  
✅ OmniRoute routes to MiroFish via `ai.aitradepulse.com`  
✅ Polyedge embeds MiroFish UI in `/mirofish` tab  
✅ Debate visualization shows MiroFish agents  
✅ Real-time streaming works  
✅ Fallback to local debate works  
✅ All tests passing  

---

## Next Steps

1. **Deploy MiroFish** - Set up infrastructure
2. **Configure OmniRoute** - Add MiroFish provider
3. **Update Polyedge** - Add UI components
4. **Test E2E** - Verify complete flow
5. **Document** - Update user guide

**Ready to start Phase 1!** 🚀
