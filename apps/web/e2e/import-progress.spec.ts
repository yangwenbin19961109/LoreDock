import { expect, test } from '@playwright/test'

test('shows honest import progress until Core finishes processing', async ({ page }) => {
  let imported = false
  let batchPolls = 0
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
    else if (path.endsWith('/import-batches') && route.request().method() === 'POST') {
      data = {
        id: 'batch',
        library_id: library.id,
        name: source.name,
        status: 'uploading',
        expected_items: 1,
        job_count: 0,
        completed_items: 0,
        succeeded_items: 0,
        duplicate_items: 0,
        failed_items: 0,
        canceled_items: 0,
        created_at: '2026-09-07',
        updated_at: '2026-09-07'
      }
    } else if (path.endsWith('/import-batches')) {
      data = { items: [], page: { limit: 20 } }
    } else if (path.endsWith('/import-batches/batch/seal')) {
      data = {
        id: 'batch',
        library_id: library.id,
        name: source.name,
        status: 'processing',
        expected_items: 1,
        job_count: 1,
        completed_items: 0,
        succeeded_items: 0,
        duplicate_items: 0,
        failed_items: 0,
        canceled_items: 0,
        created_at: '2026-09-07',
        updated_at: '2026-09-07'
      }
    } else if (path.endsWith('/import-batches/batch')) {
      batchPolls += 1
      const completed = batchPolls >= 2
      data = {
        id: 'batch',
        library_id: library.id,
        name: source.name,
        status: completed ? 'succeeded' : 'processing',
        expected_items: 1,
        job_count: 1,
        completed_items: completed ? 1 : 0,
        succeeded_items: completed ? 1 : 0,
        duplicate_items: 0,
        failed_items: 0,
        canceled_items: 0,
        created_at: '2026-09-07',
        updated_at: '2026-09-07'
      }
    } else if (path.endsWith('/sources') && route.request().method() === 'POST') {
      await new Promise((resolve) => setTimeout(resolve, 350))
      imported = true
      data = {
        source: { ...source, status: 'pending' },
        duplicate: false,
        job: {
          id: 'job',
          library_id: library.id,
          source_id: source.id,
          batch_id: 'batch',
          kind: 'index_source',
          status: 'pending',
          attempts: 0,
          progress: 0.1,
          error: null,
          created_at: '2026-09-07',
          updated_at: '2026-09-07'
        }
      }
    } else if (path.endsWith('/sources')) {
      data = { items: imported ? [source] : [], page: { limit: 10 } }
    } else if (path.endsWith('/content')) {
      data = { source_id: source.id, text: '资料内容', char_start: 0, char_end: 4 }
    } else if (path.endsWith('/favorite')) data = { favorite: false }
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
  await expect(progress).toContainText('正在索引 0/1')
  await expect(progress).toContainText('已完成 1/1')
  await expect(progress.locator('progress')).toHaveAttribute('value', '1')
})
