# Security Audit Report — polyedge
**Date:** 2026-05-04  
**Severity:** 🔴 CRITICAL

---

## Executive Summary

**CRITICAL VULNERABILITIES FOUND:** Live API keys, private keys, and secrets are committed to the repository in the `.env` file. This poses an immediate risk of unauthorized access to trading accounts, API services, and blockchain wallets.

---

## Findings

### 1. 🔴 CRITICAL: Live Secrets in `.env` File

**File:** `.env` (lines 19-87)  
**Severity:** CRITICAL  
**Status:** EXPOSED

| Secret | Line | Type | Exposure |
|--------|------|------|----------|
| `POLYMARKET_PRIVATE_KEY` | 19 | Ethereum Private Key (64 hex chars) | **LIVE WALLET** |
| `POLYMARKET_BUILDER_API_KEY` | 27 | API Key (UUID format) | Polymarket Builder Program |
| `POLYMARKET_BUILDER_SECRET` | 28 | Base64 Secret | Polymarket Builder Program |
| `POLYMARKET_BUILDER_PASSPHRASE` | 29 | Passphrase (64 hex chars) | Polymarket Builder Program |
| `POLYMARKET_RELAYER_API_KEY` | 31 | API Key (UUID format) | Polymarket Relayer |
| `KALSHI_API_KEY_ID` | 44 | API Key ID (UUID) | Kalshi Trading API |
| `GROQ_API_KEY` | 57 | LLM API Key (gsk_ prefix) — REDACTED | Groq AI Service |
| `ADMIN_API_KEY` | 87 | Admin Authentication Token | Backend Admin Access |

**Impact:**
- ✅ Attacker can trade on Polymarket with live funds
- ✅ Attacker can access Kalshi trading API
- ✅ Attacker can make LLM API calls (cost exposure)
- ✅ Attacker can access admin endpoints

---

### 2. 🔴 CRITICAL: Private Key File in Repository

**File:** `secrets/kalshi_private_key.pem`  
**Severity:** CRITICAL  
**Status:** EXPOSED (1,678 bytes, RSA private key)

**Impact:**
- ✅ Attacker can authenticate to Kalshi API
- ✅ Can execute trades on Kalshi platform

---

### 3. 🟡 HIGH: Wallet Address Exposure

**File:** `.env` (lines 24, 30, 32)  
**Severity:** HIGH  
**Status:** EXPOSED

| Address | Purpose |
|---------|---------|
| `0xAd85C2F3942561AFA448cbbD5811a5f7E2e3C6Bd` | Main trading wallet |
| `0xad85c2f3942561afa448cbbd5811a5f7e2e3c6bd` | Builder program wallet |
| `0xaae484a962a1a20f4542678f920a07589fb665fb` | Relayer wallet |

**Impact:**
- ✅ Attacker can monitor all transactions
- ✅ Can correlate trading activity to identity
- ✅ Can front-run or sandwich trades

---

### 4. 🟡 HIGH: Contract Addresses Hardcoded

**File:** `.env` (lines 35-38)  
**Severity:** MEDIUM  
**Status:** EXPOSED (but these are public contract addresses)

These are legitimate public contract addresses on Polygon, not secrets. No action needed.

---

### 5. 🟢 LOW: Test Fixtures with Mock Secrets

**Files:**
- `tests/test_admin_api.py` (lines 40-41, 62, 77, 87)
- `frontend/src/test/api.test.ts` (lines 38-39)
- `frontend/src/test/Settings.mirofish.test.tsx` (multiple lines)

**Severity:** LOW  
**Status:** ACCEPTABLE (test fixtures only, not real secrets)

These are clearly test/mock values and pose no risk.

---

## Remediation Steps

### IMMEDIATE (Within 1 hour)

1. **Rotate all exposed secrets:**
   ```bash
   # Polymarket
   - Regenerate POLYMARKET_PRIVATE_KEY (create new wallet)
   - Regenerate POLYMARKET_BUILDER_API_KEY
   - Regenerate POLYMARKET_BUILDER_SECRET
   - Regenerate POLYMARKET_BUILDER_PASSPHRASE
   - Regenerate POLYMARKET_RELAYER_API_KEY
   
   # Kalshi
   - Regenerate KALSHI_API_KEY_ID
   - Regenerate kalshi_private_key.pem
   
   # AI Services
   - Regenerate GROQ_API_KEY
   
   # Admin
   - Regenerate ADMIN_API_KEY
   ```

2. **Remove `.env` from git history:**
   ```bash
   git filter-branch --tree-filter 'rm -f .env' HEAD
   git push origin --force-with-lease
   ```

3. **Add `.env` to `.gitignore`:**
   ```bash
   echo ".env" >> .gitignore
   echo "secrets/" >> .gitignore
   git add .gitignore
   git commit -m "Add .env and secrets/ to .gitignore"
   git push origin main
   ```

### SHORT-TERM (Within 24 hours)

4. **Use environment variable management:**
   - Deploy to Railway/Vercel with secrets in platform vault
   - Use GitHub Secrets for CI/CD
   - Never commit `.env` to any branch

5. **Implement secret scanning:**
   ```bash
   # Add pre-commit hook
   pip install detect-secrets
   detect-secrets scan > .secrets.baseline
   ```

6. **Audit git history for other secrets:**
   ```bash
   git log -p | grep -i "api_key\|private_key\|secret" | head -50
   ```

### LONG-TERM (Within 1 week)

7. **Document secret management:**
   - Update `POLYMARKET_SETUP.md` with secure credential setup
   - Add `.env.example` with placeholder values only
   - Document which secrets go where (Railway, Vercel, GitHub)

8. **Enable branch protection:**
   - Require code review before merge
   - Enable status checks
   - Dismiss stale reviews on push

9. **Monitor for secret leaks:**
   - Subscribe to GitHub secret scanning alerts
   - Use `git-secrets` or `truffleHog` in CI/CD

---

## Files Requiring Action

| File | Action | Priority |
|------|--------|----------|
| `.env` | DELETE from git history, add to .gitignore | CRITICAL |
| `secrets/kalshi_private_key.pem` | DELETE from git history, add to .gitignore | CRITICAL |
| `.gitignore` | Add `.env` and `secrets/` | CRITICAL |
| `POLYMARKET_SETUP.md` | Update with secure setup instructions | HIGH |
| `.env.example` | Ensure no real values, only placeholders | HIGH |

---

## Verification Checklist

- [ ] All secrets rotated on Polymarket
- [ ] All secrets rotated on Kalshi
- [ ] All secrets rotated on Groq
- [ ] Admin API key regenerated
- [ ] `.env` removed from git history
- [ ] `secrets/` removed from git history
- [ ] `.gitignore` updated
- [ ] `.env.example` verified (no real values)
- [ ] New `.env` created locally with rotated secrets
- [ ] CI/CD updated to use platform secrets
- [ ] Team notified of secret rotation
- [ ] Monitoring enabled for future leaks

---

## References

- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [OWASP: Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [detect-secrets](https://github.com/Yelp/detect-secrets)
- [git-secrets](https://github.com/awslabs/git-secrets)


---

## Summary Table: All Secrets Found

| File | Line(s) | Secret Name | Type | Severity | Action |
|------|---------|-------------|------|----------|--------|
| `.env` | 19 | POLYMARKET_PRIVATE_KEY | Ethereum Private Key | 🔴 CRITICAL | Rotate immediately |
| `.env` | 27 | POLYMARKET_BUILDER_API_KEY | API Key | 🔴 CRITICAL | Rotate immediately |
| `.env` | 28 | POLYMARKET_BUILDER_SECRET | Base64 Secret | 🔴 CRITICAL | Rotate immediately |
| `.env` | 29 | POLYMARKET_BUILDER_PASSPHRASE | Passphrase | 🔴 CRITICAL | Rotate immediately |
| `.env` | 31 | POLYMARKET_RELAYER_API_KEY | API Key | 🔴 CRITICAL | Rotate immediately |
| `.env` | 44 | KALSHI_API_KEY_ID | API Key ID | 🔴 CRITICAL | Rotate immediately |
| `.env` | 57 | GROQ_API_KEY | LLM API Key | 🔴 CRITICAL | Rotate immediately |
| `.env` | 87 | ADMIN_API_KEY | Auth Token | 🔴 CRITICAL | Rotate immediately |
| `secrets/kalshi_private_key.pem` | — | RSA Private Key | Private Key | 🔴 CRITICAL | Regenerate & rotate |
| `.env` | 24, 30, 32 | Wallet Addresses (3x) | Ethereum Address | 🟡 HIGH | Monitor on-chain |

**Total Secrets Exposed:** 10 critical items  
**Total Files Affected:** 2 files (`.env`, `secrets/kalshi_private_key.pem`)

---

## Git History Check

**Status:** `.env` and `secrets/` are in git history and accessible via:
```bash
git log --all --full-history -- .env
git log --all --full-history -- secrets/kalshi_private_key.pem
```

**Risk:** Anyone with repository access (including forks, clones, CI/CD logs) can retrieve these secrets.

---

## Recommendations by Priority

### P0 (Do Now — Next 30 minutes)
1. Notify all team members of the breach
2. Rotate POLYMARKET_PRIVATE_KEY (create new wallet, transfer funds)
3. Rotate POLYMARKET_BUILDER credentials
4. Rotate KALSHI credentials
5. Rotate GROQ_API_KEY
6. Rotate ADMIN_API_KEY
7. Monitor Polymarket and Kalshi accounts for unauthorized activity

### P1 (Do Today — Next 4 hours)
1. Remove `.env` from git history using `git filter-branch` or `git filter-repo`
2. Remove `secrets/kalshi_private_key.pem` from git history
3. Force-push cleaned history to all branches
4. Add `.env` and `secrets/` to `.gitignore`
5. Update `.env.example` with placeholder values only
6. Verify no other `.env.*` files contain secrets

### P2 (Do This Week)
1. Set up GitHub Secrets for CI/CD
2. Configure Railway/Vercel environment variables
3. Implement pre-commit hooks to prevent future commits
4. Add secret scanning to CI/CD pipeline
5. Document secure credential setup in POLYMARKET_SETUP.md
6. Enable branch protection rules

---

## Code Review: No Hardcoded Secrets in Source

✅ **PASS:** No hardcoded API keys found in Python/TypeScript source code  
✅ **PASS:** All secrets properly referenced via environment variables  
✅ **PASS:** Test fixtures use mock/placeholder values only  

**Note:** The only issue is the `.env` file itself being committed to git.

---

## Compliance Notes

- **OWASP A02:2021** – Cryptographic Failures: Secrets exposed in version control
- **CWE-798** – Use of Hard-Coded Credentials
- **CWE-798** – Sensitive Data Exposure

---

## Audit Completed

**Auditor:** Security Scan  
**Date:** 2026-05-04  
**Status:** ✅ Complete  
**Next Review:** After remediation (within 24 hours)

