import { test, expect } from '@playwright/test'

test('unauthenticated user is redirected to /login from root', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/login')
  await expect(page.getByRole('heading', { name: 'Garmin Training Coach' })).toBeVisible()
})

test('login page shows the magic link form', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByLabel('Email')).toBeVisible()
  await expect(page.getByRole('button', { name: /Recevoir le lien/ })).toBeVisible()
})

test('protected route /today redirects unauthenticated to /login', async ({ page }) => {
  await page.goto('/today')
  await page.waitForURL('**/login')
})
