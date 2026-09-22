import { expect, test } from '@playwright/test'

test('imports a public webpage snapshot from the library toolbar', async ({ page }) => {
  let imported = false
  let submittedUrl = ''
  const source = {
    id: 'web-source',
    library_id: 'library',
    name: 'guide.html',
    media_type: 'text/html',
    status: 'ready',
    content_hash: 'hash',
    size_bytes: 42,
    source_kind: 'url',
    origin_url: 'https://example.com/guide',
    error: null,
    created_at: '2026-09-07T00:00:00Z',
    updated_at: '2026-09-07T00:00:00Z'
  }
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    let data: unknown = {}
    if (path.endsWith('/health')) {
      data = { status: 'ok', service: 'loredock-core', version: '0.1.1', api_version: 'v1' }
    } else if (path.endsWith('/settings')) {
      data = {
        onboarding_completed: true,
        theme: 'light',
        default_search_mode: 'lexical',
        updated_at: '2026-09-07T00:00:00Z'
      }
    } else if (path.endsWith('/models/default')) {
      data = {
        model_id: 'model',
        display_name: 'model',
        state: 'missing',
        active: false,
        restart_required: false,
        download_size_bytes: 0,
        required_space_bytes: 0,
        free_space_bytes: 1,
        error: null
      }
    } else if (path.endsWith('/models/jobs/latest')) {
      data = null
    } else if (path.endsWith('/libraries')) {
      data = {
        items: [
          {
            id: 'library',
            name: '网页资料',
            created_at: '2026-09-07T00:00:00Z',
            updated_at: '2026-09-07T00:00:00Z'
          }
        ],
        page: { limit: 50 }
      }
    } else if (path.endsWith('/import-batches') && request.method() === 'POST') {
      data = {
        id: 'url-batch',
        library_id: 'library',
        name: source.origin_url,
        status: 'uploading',
        expected_items: 1,
        job_count: 0,
        completed_items: 0,
        succeeded_items: 0,
        duplicate_items: 0,
        failed_items: 0,
        canceled_items: 0,
        created_at: source.created_at,
        updated_at: source.updated_at
      }
    } else if (path.endsWith('/import-batches')) {
      data = { items: [], page: { limit: 20 } }
    } else if (path.endsWith('/import-batches/url-batch/seal')) {
      data = {
        id: 'url-batch',
        library_id: 'library',
        name: source.origin_url,
        status: 'succeeded',
        expected_items: 1,
        job_count: 1,
        completed_items: 1,
        succeeded_items: 1,
        duplicate_items: 0,
        failed_items: 0,
        canceled_items: 0,
        created_at: source.created_at,
        updated_at: source.updated_at
      }
    } else if (path.endsWith('/url-sources')) {
      submittedUrl = (request.postDataJSON() as { url: string }).url
      imported = true
      data = {
        source,
        job: {
          id: 'job',
          library_id: 'library',
          source_id: source.id,
          batch_id: 'url-batch',
          kind: 'index_source',
          status: 'succeeded',
          attempts: 1,
          progress: 1,
          error: null,
          created_at: source.created_at,
          updated_at: source.updated_at
        },
        duplicate: false
      }
    } else if (path.endsWith('/sources')) {
      data = { items: imported ? [source] : [], page: { limit: 10, next_cursor: null } }
    } else if (path.endsWith('/content')) {
      data = {
        source_id: source.id,
        text: 'Imported webpage text',
        char_start: 0,
        char_end: 21
      }
    } else if (path.endsWith('/favorite')) {
      data = { favorite: false }
    }
    await route.fulfill({ status: path.endsWith('/url-sources') ? 201 : 200, json: data })
  })

  await page.goto('/')
  await page.getByRole('button', { name: '从网页导入', exact: true }).click()
  const dialog = page.getByRole('heading', { name: '从网址导入' }).locator('..')
  await dialog.getByLabel('网页地址').fill('https://example.com/guide')
  await dialog.getByRole('button', { name: '导入网页', exact: true }).click()

  await expect.poll(() => submittedUrl).toBe('https://example.com/guide')
  await expect(page.getByRole('row', { name: /guide\.html/ })).toBeVisible()
  await expect(page.locator('.document-preview')).toContainText('Imported webpage text')
  await page.getByRole('button', { name: '详情', exact: true }).click()
  await expect(page.locator('.source-details')).toContainText('https://example.com/guide')
})
