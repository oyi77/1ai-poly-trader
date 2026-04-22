# MiroFish UI Manual Testing Guide

**Created:** 2026-04-21  
**Purpose:** Complete UI verification for MiroFish integration

---

## Prerequisites

- Modern web browser (Chrome, Firefox, Safari, or Edge)
- Internet connection
- 15-20 minutes for complete testing

---

## Test Suite 1: MiroFish Standalone (10 minutes)

### URL: https://polyedge-mirofish.aitradepulse.com

#### Test 1.1: Homepage Load
- [ ] Page loads without errors
- [ ] Logo "MIROFISH" visible in top-left
- [ ] Language switcher "中文 ▼" visible in top-right
- [ ] GitHub link visible
- [ ] Hero section displays correctly
- [ ] System status panel shows "准备就绪"

#### Test 1.2: Navigation
- [ ] Click "开始模拟" button → navigates to simulation page
- [ ] Click language switcher → dropdown appears
- [ ] Switch to English → UI text changes
- [ ] Switch back to Chinese → UI text changes back
- [ ] Click GitHub link → opens in new tab

#### Test 1.3: Simulation Creation
- [ ] Navigate to simulation view
- [ ] "Create Simulation" button visible
- [ ] Click create → form appears
- [ ] Fill in simulation name
- [ ] Fill in description
- [ ] Click submit → simulation created
- [ ] New simulation appears in list

#### Test 1.4: Agent Management
- [ ] Open a simulation
- [ ] "Add Agent" button visible
- [ ] Click add agent → form appears
- [ ] Fill in agent name
- [ ] Select agent role (optimist/pessimist/analyst)
- [ ] Fill in personality
- [ ] Click submit → agent created
- [ ] Agent appears in list
- [ ] Repeat to create 3 agents total

#### Test 1.5: Debate Execution
- [ ] "Start Debate" button visible
- [ ] Click start debate → debate form appears
- [ ] Enter debate topic
- [ ] Set number of rounds
- [ ] Click start → debate begins
- [ ] Messages appear from agents
- [ ] Progress indicator updates
- [ ] Debate completes
- [ ] Prediction generated

#### Test 1.6: Results View
- [ ] Navigate to reports/results
- [ ] Completed debates listed
- [ ] Click on debate → details appear
- [ ] All messages visible
- [ ] Prediction displayed
- [ ] Confidence score shown
- [ ] Can export/download results

---

## Test Suite 2: Polyedge Dashboard (5 minutes)

### URL: https://polyedge.aitradepulse.com

#### Test 2.1: Dashboard Load
- [ ] Page loads without errors
- [ ] Navigation bar visible
- [ ] All menu items visible (Dashboard, Markets, Positions, History, Settings, MiroFish)
- [ ] Dashboard content displays
- [ ] No console errors (check browser DevTools)

#### Test 2.2: Navigation
- [ ] Click "Dashboard" → dashboard page loads
- [ ] Click "Markets" → markets page loads
- [ ] Click "Positions" → positions page loads
- [ ] Click "History" → history page loads
- [ ] Click "Settings" → settings page loads
- [ ] Click "MiroFish" → MiroFish page loads

#### Test 2.3: Page Functionality
- [ ] Dashboard: Charts render correctly
- [ ] Markets: Market data displays
- [ ] Positions: Position list shows
- [ ] History: Trade history visible
- [ ] Settings: Configuration options available

---

## Test Suite 3: MiroFish Integration (5 minutes)

### URL: https://polyedge.aitradepulse.com/mirofish

#### Test 3.1: Embedded View Load
- [ ] Page loads without errors
- [ ] Iframe visible on page
- [ ] MiroFish loads inside iframe
- [ ] MiroFish homepage visible in iframe
- [ ] No CORS errors in console

#### Test 3.2: Iframe Interaction
- [ ] Can scroll within iframe
- [ ] Can click buttons in iframe
- [ ] Can navigate within iframe
- [ ] Iframe content responsive
- [ ] No layout issues

#### Test 3.3: Full UI Button
- [ ] "Open Full UI" button visible
- [ ] Button positioned correctly
- [ ] Click button → new tab opens
- [ ] New tab loads standalone MiroFish
- [ ] URL is https://polyedge-mirofish.aitradepulse.com

#### Test 3.4: Navigation Integration
- [ ] MiroFish link highlighted when on /mirofish
- [ ] Can navigate back to dashboard
- [ ] Can navigate to other pages
- [ ] Can return to MiroFish
- [ ] State preserved when returning

---

## Test Suite 4: End-to-End Workflow (Optional, 10 minutes)

### Complete Trading Signal Flow

#### Test 4.1: Create Prediction from Polyedge
- [ ] Open Polyedge dashboard
- [ ] Navigate to MiroFish (embedded)
- [ ] Create new simulation
- [ ] Add 5 agents (mix of roles)
- [ ] Start debate on market prediction
- [ ] Wait for completion
- [ ] View prediction results

#### Test 4.2: Use Prediction for Trading
- [ ] Note prediction outcome
- [ ] Navigate back to Polyedge dashboard
- [ ] Check if prediction could inform trading decision
- [ ] Verify workflow makes sense

---

## Browser Compatibility (Optional)

Test on multiple browsers:
- [ ] Chrome/Chromium
- [ ] Firefox
- [ ] Safari (Mac only)
- [ ] Edge

---

## Mobile Responsiveness (Optional)

Test on mobile devices or browser DevTools mobile view:
- [ ] MiroFish standalone responsive
- [ ] Polyedge dashboard responsive
- [ ] Iframe embedding works on mobile
- [ ] Touch interactions work

---

## Issue Reporting Template

If you find issues, document them as:

```
**Issue:** [Brief description]
**Location:** [URL and component]
**Steps to Reproduce:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Expected:** [What should happen]
**Actual:** [What actually happens]
**Severity:** [Critical/High/Medium/Low]
**Browser:** [Browser name and version]
**Screenshot:** [If applicable]
```

---

## Success Criteria

All tests should pass with:
- ✅ No critical errors
- ✅ All navigation working
- ✅ All forms functional
- ✅ Iframe embedding working
- ✅ Predictions generating correctly

---

## Quick 5-Minute Smoke Test

If time is limited, test these critical paths:

1. **MiroFish Standalone:**
   - Open https://polyedge-mirofish.aitradepulse.com
   - Verify homepage loads
   - Click "开始模拟" → verify navigation works

2. **Polyedge Dashboard:**
   - Open https://polyedge.aitradepulse.com
   - Verify dashboard loads
   - Click each nav item → verify pages load

3. **Integration:**
   - Click "MiroFish" in nav
   - Verify iframe loads MiroFish
   - Click "Open Full UI" → verify opens in new tab

If all 3 pass, integration is working correctly.

---

**Testing Status:** ⚠️ PENDING USER VERIFICATION  
**Estimated Time:** 15-20 minutes (full), 5 minutes (smoke test)  
**Priority:** Medium (system is functional, testing confirms UX)
