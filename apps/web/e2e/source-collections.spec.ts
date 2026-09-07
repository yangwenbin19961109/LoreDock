import { expect, test } from '@playwright/test'

for (const theme of ['light', 'dark']) {
  test(`recent and favorites ${theme}`, async ({ page }) => {
    await page.setViewportSize({
      width: theme === 'light' ? 1240 : 1600,
      height: theme === 'light' ? 820 : 1000
    })
    let favorite = false
    let visits = 0
    const source = {
      id: 'source-fixture',
      library_id: 'lib',
      name: '知识库设计与开发文档.md',
      status: 'ready',
      media_type: 'text/markdown',
      size_bytes: 20,
      created_at: '2026-09-04',
      updated_at: '2026-09-04'
    }
    await page.route('**/api/v1/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      let data: unknown = {}
      if (path.endsWith('/health')) data = { status: 'ok', version: '0.1.0' }
      else if (path.endsWith('/settings'))
        data = { onboarding_completed: true, theme, default_search_mode: 'lexical' }
      else if (path.endsWith('/libraries'))
        data = {
          items: [
            { id: 'lib', name: '测试知识库', created_at: '2026-09-04', updated_at: '2026-09-04' }
          ],
          page: {}
        }
      else if (path.endsWith('/models/jobs/latest')) data = null
      else if (path.endsWith('/sources')) data = { items: [source], page: {} }
      else if (path.endsWith('/favorite')) {
        if (route.request().method() === 'PUT')
          favorite = (route.request().postDataJSON() as { favorite: boolean }).favorite
        data = { favorite }
      } else if (path.endsWith('/visit')) {
        visits++
        await route.fulfill({ status: 204 })
        return
      } else if (path.includes('/source-collections/'))
        data = {
          items: (path.endsWith('/favorites') ? favorite : visits > 0) ? [source] : [],
          page: { next_cursor: null }
        }
      else if (path.endsWith('/content'))
        data = {
          source_id: source.id,
          text: '安全的资料预览 <script>alert(1)</script>\n'.repeat(12),
          char_start: 0,
          char_end: 30
        }
      await route.fulfill({ json: data })
    })
    await page.goto('/')
    await expect(page.getByRole('button', { name: '收藏资料', exact: true })).toBeEnabled()
    expect(visits).toBe(0)
    await page.locator('button.source-row').first().click()
    await expect.poll(() => visits).toBe(1)
    await page.getByRole('button', { name: '收藏资料', exact: true }).click()
    await expect(page.getByRole('button', { name: '取消收藏', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '收藏', exact: true }).click()
    const listSurfaceContrast = await page.locator('.collection-list-pane').evaluate((element) => {
      const pageBackground = getComputedStyle(element.closest('.collection-area')!).backgroundColor
      return getComputedStyle(element).backgroundColor !== pageBackground
    })
    expect(listSurfaceContrast).toBe(true)
    await page.getByRole('button', { name: /知识库设计与开发文档/ }).click()
    await expect(page.locator('.collection-preview')).toContainText('安全的资料预览')
    await expect.poll(() => visits).toBe(2)
    await page.screenshot({ path: `test-results/collections-${theme}.png` })
    expect(
      await page
        .locator('.collection-area')
        .evaluate((element) => element.scrollWidth > element.clientWidth)
    ).toBe(false)
    await page
      .getByRole('button', { name: /测试知识库/ })
      .first()
      .click()
    await expect(page.locator('button.source-row')).toHaveCount(1)
    await expect(page.locator('button.source-row').first()).toContainText(source.name)
    await expect(page.locator('.detail-actions').getByRole('button')).toHaveCount(2)
    await expect(page.getByRole('button', { name: '删除资料', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '收藏', exact: true }).click()
    await page.getByRole('button', { name: /知识库设计与开发文档/ }).click()
    await page.getByRole('button', { name: '取消收藏', exact: true }).click()
    await expect(page.getByText('还没有收藏。请在资料预览中点击“收藏资料”。')).toBeVisible()
    await page.getByRole('button', { name: '最近使用', exact: true }).click()
    await expect(page.getByRole('button', { name: /知识库设计与开发文档/ })).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: '最近使用', exact: true }).click()
    await expect(page.getByRole('button', { name: /知识库设计与开发文档/ })).toBeVisible()
  })
}
