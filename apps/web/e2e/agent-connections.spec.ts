import { expect, test, type Locator } from '@playwright/test'

async function expectUnclippedFocus(field: Locator) {
  await expect(field).toBeFocused()
  const metrics = await field.evaluate((element) => {
    const style = getComputedStyle(element)
    const bounds = element.getBoundingClientRect()
    const outside = Math.max(0, parseFloat(style.outlineWidth) + parseFloat(style.outlineOffset))
    const clippedBy: string[] = []
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      if (getComputedStyle(parent).overflowX === 'visible') continue
      const box = parent.getBoundingClientRect()
      if (
        bounds.left - outside < box.left + parent.clientLeft - 0.5 ||
        bounds.right + outside > box.left + parent.clientLeft + parent.clientWidth + 0.5
      ) {
        clippedBy.push(parent.className)
      }
    }
    return { width: parseFloat(style.outlineWidth), style: style.outlineStyle, clippedBy }
  })
  expect(metrics.width).toBeGreaterThanOrEqual(2)
  expect(metrics.style).toBe('solid')
  expect(metrics.clippedBy).toEqual([])
}

for (const variant of [
  { width: 1240, height: 820, theme: 'light' },
  { width: 1240, height: 820, theme: 'dark' },
  { width: 1600, height: 1000, theme: 'light' },
  { width: 1600, height: 1000, theme: 'dark' }
]) {
  test(`Agent setup flow ${variant.theme} ${variant.width}`, async ({ page, context }) => {
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
      if (path.endsWith('/health')) data = { status: 'ok', version: '0.1.1' }
      else if (path.endsWith('/libraries')) data = { items: [library], page: { limit: 50 } }
      else if (path.endsWith('/settings'))
        data = { onboarding_completed: true, theme: variant.theme, default_search_mode: 'lexical' }
      else if (path.endsWith('/models/jobs/latest')) data = null
      else if (path.endsWith('/sources')) data = { items: [], page: { limit: 10 } }
      else if (path.endsWith('/diagnostics')) {
        const payload = route.request().postDataJSON() as { query?: string; library_id?: string }
        if (payload.query) expect(payload.library_id).toBe(library.id)
        data = {
          scope: 'local_core',
          external_agent_verified: false,
          status: payload.query ? 'no_matches' : 'passed',
          stage: payload.query ? 'search' : 'libraries',
          code: payload.query ? 'no_matches' : 'local_check_passed',
          completed: payload.query
            ? ['credential', 'setup', 'libraries', 'search']
            : ['credential', 'setup', 'libraries'],
          hit_count: 0
        }
      } else if (path.endsWith('/agent-connections')) {
        if (route.request().method() === 'POST') {
          created = true
          data = connection
        } else data = { items: created ? [connection] : [] }
      } else if (path.endsWith('/setup'))
        data = {
          instructions:
            '请添加 LoreDock MCP。保留已有服务，调用 list_libraries 验证。\n' +
            '本地开发连接说明。'.repeat(50),
          runtime: 'development',
          configurations: {
            codex:
              '[mcp_servers."loredock-connection-fixture"]\ncommand = "C:\\\\Program Files\\\\LoreDock\\\\loredock-mcp.exe"\nargs = ["--connection", "connection-fixture"]',
            cursor: JSON.stringify(
              {
                mcpServers: {
                  'loredock-connection-fixture': {
                    type: 'stdio',
                    command: 'C:\\Program Files\\LoreDock\\loredock-mcp.exe',
                    args: ['--connection', 'connection-fixture']
                  }
                }
              },
              null,
              2
            )
          }
        }
      else if (route.request().method() === 'DELETE') {
        created = false
        data = { revoked: true, credential_removed: true }
      }
      await route.fulfill({ json: data })
    })
    await page.goto('/')
    await page.getByRole('button', { name: 'Agent 连接' }).click()
    const name = page.getByLabel('连接名称', { exact: true })
    await name.click()
    await expectUnclippedFocus(name)
    await name.press('Tab')
    await page.keyboard.press('Shift+Tab')
    await expectUnclippedFocus(name)
    await name.press('ControlOrMeta+A')
    await expect(name).toHaveValue('我的 Agent')
    await page.screenshot({ path: `test-results/agent-name-${variant.theme}-${variant.width}.png` })
    await expect(page.getByRole('button', { name: '生成连接说明' })).toBeDisabled()
    await page.getByRole('checkbox', { name: library.name }).check()
    await page.getByRole('button', { name: '生成连接说明' }).click()
    await expect(page.getByLabel('连接说明（可手动选择复制）')).toContainText('list_libraries')
    await expect(page.getByRole('button', { name: '复制连接说明' })).toBeVisible()
    await page.getByRole('button', { name: '复制连接说明' }).click()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('list_libraries')
    await page.keyboard.press('Tab')
    const instructions = page.getByLabel('连接说明（可手动选择复制）')
    await expectUnclippedFocus(instructions)
    await instructions.click()
    await expectUnclippedFocus(instructions)
    await instructions.press('ControlOrMeta+A')
    expect(
      await instructions.evaluate(
        (element: HTMLTextAreaElement) => element.selectionEnd - element.selectionStart
      )
    ).toBe((await instructions.inputValue()).length)
    await instructions.press('ControlOrMeta+C')
    // Native Windows copy normalizes textarea newlines to CRLF.
    expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n')).toBe(
      await instructions.inputValue()
    )
    await page.screenshot({
      path: `test-results/agent-${variant.theme}-${variant.width}.png`,
      fullPage: true
    })
    const overflow = await page
      .locator('.agent-area')
      .evaluate((element) => element.scrollWidth > element.clientWidth)
    expect(overflow).toBe(false)
    await page.getByText('Agent 没能自动配置？手动添加', { exact: true }).click()
    const config = page.getByLabel('Codex 配置（TOML，可手动选择复制）')
    await expect(config).toHaveValue(/mcp_servers/)
    await page.getByRole('button', { name: '复制 Codex 配置' }).click()
    expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n')).toBe(
      await config.inputValue()
    )
    await config.click()
    await expectUnclippedFocus(config)
    await page.getByLabel('选择客户端').selectOption('cursor')
    const cursorConfig = page.getByLabel('Cursor 配置（JSON，可手动选择复制）')
    await expect(cursorConfig).toHaveValue(/mcpServers/)
    await page.getByRole('button', { name: '复制 Cursor 配置' }).click()
    expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n')).toBe(
      await cursorConfig.inputValue()
    )
    await page.evaluate(() => {
      Object.defineProperty(navigator.clipboard, 'writeText', {
        configurable: true,
        value: () => Promise.reject(new Error('denied'))
      })
    })
    await page.getByRole('button', { name: '复制 Cursor 配置' }).click()
    await expect(page.getByText('无法访问剪贴板，请选中下方配置并手动复制。')).toBeVisible()
    await cursorConfig.click()
    await expectUnclippedFocus(cursorConfig)
    await page.screenshot({
      path: `test-results/agent-manual-${variant.theme}-${variant.width}.png`
    })
    expect(
      await page.locator('.agent-copy').evaluate((el) => el.scrollWidth > el.clientWidth)
    ).toBe(false)
    await page.getByText('检查连接', { exact: true }).click()
    await page.getByRole('button', { name: '运行本地自检' }).click()
    await expect(page.getByText('本次本地自检通过。')).toBeVisible()
    await expect(page.getByText('命中引用读取：未检查')).toBeVisible()
    await page.getByLabel('测试关键词（可选）').fill('missing fixture')
    await expect(page.getByText('本次本地自检通过。')).toHaveCount(0)
    await page.getByRole('button', { name: '运行本地自检' }).click()
    await expect(page.getByText('搜索已完成，但没有命中；请换用资料中的关键词。')).toBeVisible()
    await page.locator('.agent-diagnostics').scrollIntoViewIfNeeded()
    await page.screenshot({
      path: `test-results/agent-diagnostics-${variant.theme}-${variant.width}.png`
    })
    expect(
      await page.locator('.agent-columns > div').evaluate((el) => el.scrollWidth > el.clientWidth)
    ).toBe(false)
    await page.route('**/diagnostics', async (route) => {
      await route.fulfill({
        json: {
          scope: 'local_core',
          external_agent_verified: false,
          status: 'failed',
          stage: 'credential',
          code: 'credential_missing',
          completed: [],
          hit_count: 0
        }
      })
    })
    await page.getByRole('button', { name: '运行本地自检' }).click()
    await expect(page.getByText('凭据缺失或不匹配，请重新创建连接。')).toBeVisible()
    await expect(page.getByText('系统凭据与授权：失败')).toBeVisible()
    await page.route('**/diagnostics', async (route) => {
      await route.fulfill({ status: 503, json: {} })
    })
    await page.getByRole('button', { name: '运行本地自检' }).click()
    await expect(page.getByRole('alert')).toContainText('未能完成检查')
    await expect(page.getByRole('button', { name: '运行本地自检' })).toBeEnabled()
    await expect(page.getByText('系统凭据与授权：失败')).toHaveCount(0)
    await page.getByRole('button', { name: '撤销连接', exact: true }).click()
    await page.getByRole('button', { name: '确认撤销' }).click()
    await expect(page.getByLabel('连接说明（可手动选择复制）')).toHaveCount(0)
    await expect(page.locator('#agent-manual-config')).toHaveCount(0)
    await expect(page.locator('.agent-diagnostics')).toHaveCount(0)
    await expect(page.getByText('连接已撤销，Agent 不再能通过它访问知识库。')).toBeVisible()
  })
}
