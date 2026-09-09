import { expect, test } from '@playwright/test'

test('creates and verifies a managed backup from settings', async ({ page }) => {
  let backups: unknown[] = []
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    let data: unknown = {}
    if (path.endsWith('/health'))
      data = { status: 'ok', service: 'loredock-core', version: '0.1.0', api_version: 'v1' }
    else if (path.endsWith('/settings'))
      data = {
        onboarding_completed: true,
        theme: 'light',
        default_search_mode: 'lexical',
        updated_at: '2026-09-09'
      }
    else if (path.endsWith('/libraries')) data = { items: [], page: { limit: 50 } }
    else if (path.endsWith('/models/jobs/latest')) data = null
    else if (path.endsWith('/models/default'))
      data = {
        model_id: 'model',
        display_name: '模型',
        state: 'missing',
        active: false,
        restart_required: false,
        download_size_bytes: 0,
        required_space_bytes: 0,
        free_space_bytes: 1,
        error: null
      }
    else if (path.endsWith('/backups') && method === 'POST') {
      const backup = {
        id: '11111111-1111-4111-8111-111111111111',
        created_at: '2026-09-09T01:00:00Z',
        size_bytes: 4096,
        file_count: 4,
        status: 'valid'
      }
      backups = [backup]
      data = backup
    } else if (path.endsWith('/backups')) data = { items: backups, page: { limit: 200 } }
    else if (path.endsWith('/verify')) data = backups[0]
    await route.fulfill({ json: data })
  })

  await page.goto('/')
  await page.getByRole('button', { name: /设置/ }).click()
  await expect(page.getByRole('region', { name: '备份与恢复' })).toBeVisible()
  await page.getByRole('button', { name: '立即备份' }).click()
  await expect(page.getByText(/4 个文件 · 完整/)).toBeVisible()
  await page.getByRole('button', { name: '校验' }).click()
  await expect(page.getByRole('button', { name: '恢复' })).toBeEnabled()
})
