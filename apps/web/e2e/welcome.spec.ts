import { expect, test } from '@playwright/test'

test('renders the Phase 0 application shell', async ({ page }) => {
  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: '把知识安放好，再交给 Agent 使用。' })
  ).toBeVisible()
  await expect(page.getByRole('status')).toContainText('LoreDock Core')
})
