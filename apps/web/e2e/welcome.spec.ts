import { expect, test } from '@playwright/test'

test('renders the current library shell when Core is unavailable', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: '开始使用 LoreDock' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('Core')
})
