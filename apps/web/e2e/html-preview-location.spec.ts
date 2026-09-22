import { expect, test } from '@playwright/test'

test('an HTML search hit loads its source window and scrolls the preview', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 })
  const sourceText = `${Array.from(
    { length: 900 },
    (_, index) => `HTML 前置段落 ${String(index).padStart(4, '0')}。\n\n`
  ).join('')}需要定位的 HTML 关键内容。\n\n尾部内容。`
  const matchText = '需要定位的 HTML 关键内容'
  const matchStart = sourceText.indexOf(matchText)
  const matchEnd = matchStart + matchText.length
  const source = {
    id: 'html-source',
    library_id: 'lib',
    name: '长篇资料.html',
    status: 'ready',
    media_type: 'text/html',
    size_bytes: sourceText.length,
    created_at: '2026-09-07',
    updated_at: '2026-09-07'
  }
  const contentRequests: string[] = []

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let data: unknown = {}
    if (path.endsWith('/health')) data = { status: 'ok', version: '0.1.1' }
    else if (path.endsWith('/settings'))
      data = { onboarding_completed: true, theme: 'light', default_search_mode: 'lexical' }
    else if (path.endsWith('/libraries'))
      data = {
        items: [
          { id: 'lib', name: 'HTML 验收库', created_at: '2026-09-07', updated_at: '2026-09-07' }
        ],
        page: {}
      }
    else if (path.endsWith('/models/jobs/latest')) data = null
    else if (path.endsWith('/sources')) data = { items: [source], page: {} }
    else if (path.endsWith('/search'))
      data = {
        items: [
          {
            chunk_id: 'chunk-html',
            source_id: source.id,
            text: matchText,
            score: 0.032,
            char_start: matchStart,
            char_end: matchEnd,
            page: null,
            title_path: [],
            matched_chunk_id: 'chunk-html',
            parent_id: null,
            context_id: 'chunk-html',
            context_text: matchText,
            matched_range: {
              char_start: matchStart,
              char_end: matchEnd,
              page_start: null,
              page_end: null
            },
            context_range: {
              char_start: matchStart,
              char_end: matchEnd,
              page_start: null,
              page_end: null
            }
          }
        ]
      }
    else if (path.endsWith('/content')) {
      contentRequests.push(url.toString())
      const start = Number(url.searchParams.get('start') ?? 0)
      const end = Number(url.searchParams.get('end') ?? 8000)
      data = {
        source_id: source.id,
        text: sourceText.slice(start, end),
        char_start: start,
        char_end: Math.min(end, sourceText.length)
      }
    } else if (path.endsWith('/visit')) {
      await route.fulfill({ status: 204 })
      return
    }
    await route.fulfill({ json: data })
  })

  await page.goto('/')
  await expect(page.locator('.preview-document')).toContainText('HTML 前置段落 0000')
  contentRequests.length = 0
  await page.getByPlaceholder('搜索这个知识库').fill('HTML 关键内容')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.locator('.result-card').click()
  await page.getByRole('button', { name: '详情', exact: true }).click()
  await expect(
    page.getByLabel('资料详情').getByText(`字符 ${matchStart}–${matchEnd}`, { exact: true })
  ).toBeVisible()
  await page.getByRole('button', { name: '预览', exact: true }).click()

  await expect
    .poll(() => contentRequests.some((url) => url.includes(`start=${matchStart - 2000}`)))
    .toBe(true)

  const highlight = page.locator('[data-preview-highlight="true"]')
  await expect(highlight).toHaveText(matchText)
  await expect
    .poll(() => page.locator('.document-preview').evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0)
})
