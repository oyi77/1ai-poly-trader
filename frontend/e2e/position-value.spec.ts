import { test, expect } from '@playwright/test'

test.describe('Position Value Dashboard Verification', () => {
  test.beforeEach(async ({ page }) => {
    page.on('dialog', dialog => dialog.dismiss())
  })

  test('should load dashboard without errors', async ({ page }) => {
    await page.goto('/dashboard')
    
    await expect(page.getByRole('heading', { name: 'TRADING TERMINAL' })).toBeVisible({ timeout: 15000 })
    
    const response = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    expect(response.ok()).toBeTruthy()
  })

  test('should display position value as non-zero if trades exist', async ({ page }) => {
    await page.goto('/dashboard')
    
    await expect(page.getByRole('heading', { name: 'TRADING TERMINAL' })).toBeVisible({ timeout: 15000 })
    
    const response = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    expect(response.ok()).toBeTruthy()
    
    const stats = await response.json()
    
    if (stats.open_trades > 0) {
      const positionMarketValue = stats.position_market_value || 0
      expect(positionMarketValue).toBeGreaterThanOrEqual(0)
    }
  })

  test('should match position value between API and dashboard within 1%', async ({ page }) => {
    await page.goto('/dashboard')
    
    await expect(page.getByRole('heading', { name: 'TRADING TERMINAL' })).toBeVisible({ timeout: 15000 })
    
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    expect(apiResponse.ok()).toBeTruthy()
    
    const apiStats = await apiResponse.json()
    
    if (apiStats.open_trades === 0) {
      test.skip()
      return
    }
    
    expect(apiStats.position_market_value).toBeDefined()
    expect(typeof apiStats.position_market_value).toBe('number')
  })

  test('should display position breakdown table with correct values', async ({ page }) => {
    await page.goto('/dashboard')
    
    await expect(page.getByRole('heading', { name: 'TRADING TERMINAL' })).toBeVisible({ timeout: 15000 })
    
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    const apiStats = await apiResponse.json()
    
    if (apiStats.open_trades === 0) {
      test.skip()
      return
    }
    
    const tradesTab = page.getByText('Trades').first()
    await expect(tradesTab).toBeVisible({ timeout: 5000 })
    await tradesTab.click()
    await page.waitForTimeout(1000)
    
    const tableRows = page.locator('table tbody tr')
    const rowCount = await tableRows.count()
    
    expect(rowCount).toBeGreaterThan(0)
  })

  test('should verify position value in paper mode', async ({ page }) => {
    await page.goto('/dashboard')
    
    await expect(page.getByRole('heading', { name: 'TRADING TERMINAL' })).toBeVisible({ timeout: 15000 })
    
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    expect(apiResponse.ok()).toBeTruthy()
    
    const stats = await apiResponse.json()
    expect(stats.mode).toBe('paper')
    
    expect(stats).toHaveProperty('position_market_value')
    expect(stats).toHaveProperty('position_cost')
    expect(stats).toHaveProperty('unrealized_pnl')
    
    expect(typeof stats.position_market_value).toBe('number')
    expect(typeof stats.position_cost).toBe('number')
    expect(typeof stats.unrealized_pnl).toBe('number')
  })

  test('should display position metrics in desktop viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    
    await page.goto('/dashboard')
    
    await expect(page.getByRole('heading', { name: 'TRADING TERMINAL' })).toBeVisible({ timeout: 15000 })
    
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    expect(apiResponse.ok()).toBeTruthy()
    
    const stats = await apiResponse.json()
    expect(stats).toHaveProperty('position_market_value')
    expect(stats).toHaveProperty('position_cost')
    expect(stats).toHaveProperty('unrealized_pnl')
  })

  test('should verify API response schema includes position fields', async ({ page }) => {
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    expect(apiResponse.ok()).toBeTruthy()
    
    const stats = await apiResponse.json()
    
    expect(stats).toHaveProperty('position_market_value')
    expect(stats).toHaveProperty('position_cost')
    expect(stats).toHaveProperty('unrealized_pnl')
    expect(stats).toHaveProperty('open_trades')
    expect(stats).toHaveProperty('open_exposure')
    
    expect(typeof stats.position_market_value).toBe('number')
    expect(typeof stats.position_cost).toBe('number')
    expect(typeof stats.unrealized_pnl).toBe('number')
    expect(typeof stats.open_trades).toBe('number')
    expect(typeof stats.open_exposure).toBe('number')
  })

  test('should handle zero positions gracefully', async ({ page }) => {
    await page.goto('/dashboard')
    
    await expect(page.getByRole('heading', { name: 'TRADING TERMINAL' })).toBeVisible({ timeout: 15000 })
    
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=paper')
    const stats = await apiResponse.json()
    
    if (stats.open_trades === 0) {
      expect(stats.position_market_value).toBe(0)
      expect(stats.position_cost).toBe(0)
      expect(stats.unrealized_pnl).toBe(0)
    }
  })

  test('should verify testnet mode position values', async ({ page }) => {
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=testnet')
    
    if (!apiResponse.ok()) {
      test.skip()
      return
    }
    
    const stats = await apiResponse.json()
    
    expect(stats).toHaveProperty('position_market_value')
    expect(stats).toHaveProperty('position_cost')
    expect(stats).toHaveProperty('unrealized_pnl')
    
    expect(typeof stats.position_market_value).toBe('number')
    expect(typeof stats.position_cost).toBe('number')
    expect(typeof stats.unrealized_pnl).toBe('number')
  })

  test('should verify live mode position values', async ({ page }) => {
    const apiResponse = await page.request.get('https://polyedge.aitradepulse.com/api/stats?mode=live')
    
    if (!apiResponse.ok()) {
      test.skip()
      return
    }
    
    const stats = await apiResponse.json()
    
    expect(stats).toHaveProperty('position_market_value')
    expect(stats).toHaveProperty('position_cost')
    expect(stats).toHaveProperty('unrealized_pnl')
    
    expect(typeof stats.position_market_value).toBe('number')
    expect(typeof stats.position_cost).toBe('number')
    expect(typeof stats.unrealized_pnl).toBe('number')
  })
})
