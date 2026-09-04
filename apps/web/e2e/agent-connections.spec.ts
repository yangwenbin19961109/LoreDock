import { expect, test } from '@playwright/test'

for (const variant of [
  { width: 1240, height: 820, theme: 'light' },
  { width: 1600, height: 1000, theme: 'dark' }
]) {
  test(`Agent setup flow ${variant.theme}`, async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await page.setViewportSize(variant)
    const library = {
      id: 'library-fixture',
      name: '测试知识库',
      created_at: '2026-09-04',
      updated_at: '2026-09-04'
    }
    const connection = {
      id: 'connection-fixture',
      name: '我的 Agent',
      library_ids: [library.id],
      created_at: '2026-09-04'
    }
    let created = false
    await page.route('**/api/v1/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      let data: unknown = {}
      if (path.endsWith('/health')) data = { status: 'ok', version: '0.1.0' }
      else if (path.endsWith('/libraries')) data = { items: [library], page: { limit: 50 } }
      else if (path.endsWith('/settings'))
        data = { onboarding_completed: true, theme: variant.theme, default_search_mode: 'lexical' }
      else if (path.endsWith('/models/jobs/latest')) data = null
      else if (path.endsWith('/sources')) data = { items: [], page: { limit: 10 } }
      else if (path.endsWith('/agent-connections')) {
        if (route.request().method() === 'POST') {
          created = true
          data = connection
        } else data = { items: created ? [connection] : [] }
      } else if (path.endsWith('/setup'))
        data = {
          instructions:
            '请添加 LoreDock MCP。保留已有服务，调用 list_libraries 验证。\n' +
            '本地开发连接说明。'.repeat(50),
          runtime: 'development'
        }
      else if (route.request().method() === 'DELETE') {
        created = false
        data = { revoked: true, credential_removed: true }
      }
      await route.fulfill({ json: data })
    })
    await page.goto('/')
    await page.getByRole('button', { name: 'Agent 连接' }).click()
    await expect(page.getByRole('button', { name: '生成连接说明' })).toBeDisabled()
    await page.getByRole('checkbox', { name: library.name }).check()
    await page.getByRole('button', { name: '生成连接说明' }).click()
    await expect(page.getByLabel('连接说明（可手动选择复制）')).toContainText('list_libraries')
    await expect(page.getByRole('button', { name: '复制连接说明' })).toBeVisible()
    await page.getByRole('button', { name: '复制连接说明' }).click()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('list_libraries')
    await page.screenshot({ path: `test-results/agent-${variant.theme}.png`, fullPage: true })
    const overflow = await page
      .locator('.agent-area')
      .evaluate((element) => element.scrollWidth > element.clientWidth)
    expect(overflow).toBe(false)
    await page.getByRole('button', { name: '撤销连接', exact: true }).click()
    await page.getByRole('button', { name: '确认撤销' }).click()
    await expect(page.getByLabel('连接说明（可手动选择复制）')).toHaveCount(0)
    await expect(page.getByText('连接已撤销，Agent 不再能通过它访问知识库。')).toBeVisible()
  })
}
