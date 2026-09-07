import { expect, test } from '@playwright/test'

test('shows honest import progress until Core finishes processing', async ({ page }) => {
  const library = {
    id: 'lib',
    name: '导入验收库',
    created_at: '2026-09-07',
    updated_at: '2026-09-07'
  }
  const source = {
    id: 'source-imported',
    library_id: library.id,
    name: '验收资料.html',
    status: 'ready',
    media_type: 'text/html',
    content_hash: 'hash',
    size_bytes: 30,
    error: null,
    created_at: '2026-09-07',
    updated_at: '2026-09-07'
  }

  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown = {}
    if (path.endsWith('/health'))
      data = { status: 'ok', service: 'loredock-core', version: '0.1.0', api_version: 'v1' }
    else if (path.endsWith('/settings'))
      data = {
        onboarding_completed: true,
        theme: 'light',
        default_search_mode: 'lexical',
        updated_at: '2026-09-07'
      }
    else if (path.endsWith('/libraries')) data = { items: [library], page: { limit: 50 } }
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
    else if (path.endsWith('/models/jobs/latest')) data = null
    else if (path.endsWith('/sources') && route.request().method() === 'POST') {
      await new Promise((resolve) => setTimeout(resolve, 350))
      data = {
        source,
        duplicate: false,
        job: {
          id: 'job',
          library_id: library.id,
          source_id: source.id,
          kind: 'index_source',
          status: 'succeeded',
          attempts: 1,
          progress: 1,
          error: null,
          created_at: '2026-09-07',
          updated_at: '2026-09-07'
        }
      }
    } else if (path.endsWith('/sources')) data = { items: [], page: { limit: 10 } }
    await route.fulfill({ json: data })
  })

  await page.goto('/')
  await page.locator('input[type="file"]:not([webkitdirectory])').setInputFiles({
    name: source.name,
    mimeType: source.media_type,
    buffer: Buffer.from('<p>资料内容</p>')
  })

  const progress = page.getByRole('status', { name: '资料导入进度' })
  await expect(progress).toContainText('正在处理 1/1')
  await expect(progress.locator('progress')).not.toHaveAttribute('value')
  await expect(progress).toContainText('已完成 1/1')
  await expect(progress.locator('progress')).toHaveAttribute('value', '1')
})
