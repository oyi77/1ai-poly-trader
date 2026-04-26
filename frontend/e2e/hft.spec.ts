import { test, expect } from '@playwright/test'

test.describe('HFT Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    page.on('dialog', dialog => dialog.dismiss())
  })

  test('should display HFT tab in dashboard', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText('PolyEdge')).toBeVisible({ timeout: 15000 })

    const hftTab = page.getByText('HFT').first()
    await expect(hftTab).toBeVisible({ timeout: 5000 })
    await hftTab.click()
    await page.waitForTimeout(1000)
  })

  test('should show HFT strategies section', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText('PolyEdge')).toBeVisible({ timeout: 15000 })

    const hftTab = page.getByText('HFT').first()
    await hftTab.click()
    await page.waitForTimeout(1000)

    await expect(page.getByText('HFT Strategies').first()).toBeVisible({ timeout: 5000 })
  })

  test('should display HFT metrics row', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText('PolyEdge')).toBeVisible({ timeout: 15000 })

    const hftTab = page.getByText('HFT').first()
    await hftTab.click()
    await page.waitForTimeout(1000)

    await expect(page.getByText('Signals/s')).toBeVisible({ timeout: 5000 })
  })

  test('should show live signal feed', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText('PolyEdge')).toBeVisible({ timeout: 15000 })

    const hftTab = page.getByText('HFT').first()
    await hftTab.click()
    await page.waitForTimeout(1000)

    await expect(page.getByText('Live HFT Signals')).toBeVisible({ timeout: 5000 })
  })

  test('should have Live indicator in signal feed', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText('PolyEdge')).toBeVisible({ timeout: 15000 })

    const hftTab = page.getByText('HFT').first()
    await hftTab.click()
    await page.waitForTimeout(1000)

    await expect(page.getByText('Live').first()).toBeVisible({ timeout: 5000 })
  })
})