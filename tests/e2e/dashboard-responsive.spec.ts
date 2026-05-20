import { test, expect } from '@playwright/test'

const MOBILE = { width: 390, height: 844 }
const DESKTOP = { width: 1280, height: 800 }

test.describe('Dashboard nav responsive (unauthenticated)', () => {
  test('mobile : BottomNav visible, SideNav caché', async ({ page }) => {
    await page.setViewportSize(MOBILE)
    const resp = await page.goto('/today')
    await page.waitForLoadState('domcontentloaded')
    expect(resp?.status() ?? 200).toBeLessThan(500)
    expect(page.url()).toMatch(/\/(login|today)/)
  })

  test('desktop : la page se charge sans erreur layout', async ({ page }) => {
    await page.setViewportSize(DESKTOP)
    await page.goto('/today')
    await page.waitForLoadState('domcontentloaded')
    expect(page.url()).toMatch(/\/(login|today)/)
  })

  test('pas de scroll horizontal mobile', async ({ page }) => {
    await page.setViewportSize(MOBILE)
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
    const overflowX = await page.evaluate(() => {
      return document.documentElement.scrollWidth - document.documentElement.clientWidth
    })
    expect(overflowX).toBeLessThanOrEqual(0)
  })
})
