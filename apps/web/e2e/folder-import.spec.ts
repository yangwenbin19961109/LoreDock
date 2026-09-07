import { expect, test } from '@playwright/test'
import path from 'node:path'

test('preflights a folder and imports only supported files after confirmation', async ({
  page
}) => {
  let uploadCount = 0
  const source = {
    id: 'folder-source',
    library_id: 'library',
    name: 'guide.md',
    media_type: 'text/markdown',
    status: 'ready',
    content_hash: 'hash',
    size_bytes: 12,
    source_kind: 'file',
    origin_url: null,
    error: null,
    created_at: '2026-09-07T00:00:00Z',
    updated_at: '2026-09-07T00:00:00Z'
  }
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    let data: unknown = {}
    let status = 200
    if (path.endsWith('/health')) {
      data = { status: 'ok', service: 'loredock-core', version: '0.1.0', api_version: 'v1' }
    } else if (path.endsWith('/settings')) {
      data = {
        onboarding_completed: true,
        theme: 'light',
        default_search_mode: 'lexical',
        updated_at: source.updated_at
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
            name: '文件夹资料',
            created_at: source.created_at,
            updated_at: source.updated_at
          }
        ],
        page: { limit: 50 }
      }
    } else if (path.endsWith('/sources') && request.method() === 'POST') {
      uploadCount += 1
      status = 201
      data = {
        source,
        job: {
          id: 'job',
          library_id: 'library',
          source_id: source.id,
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
      data = { items: uploadCount ? [source] : [], page: { limit: 10, next_cursor: null } }
    } else if (path.endsWith('/content')) {
      data = { source_id: source.id, text: 'folder guide', char_start: 0, char_end: 12 }
    } else if (path.endsWith('/favorite')) {
      data = { favorite: false }
    }
    await route.fulfill({ status, json: data })
  })

  await page.goto('/')
  await page
    .locator('input[webkitdirectory]')
    .setInputFiles(path.resolve('apps/web/e2e/fixtures/folder-import'))

  const dialog = page.getByRole('dialog', { name: /导入/ })
  await expect(dialog).toContainText('2可导入')
  await expect(dialog).toContainText('1将跳过')
  expect(uploadCount).toBe(0)
  await dialog.getByRole('button', { name: '导入 2 份资料' }).click()

  await expect.poll(() => uploadCount).toBe(2)
  await expect(page.getByRole('row', { name: /guide\.md/ })).toBeVisible()
  await expect(page.getByRole('status', { name: '资料导入进度' })).toContainText('跳过 1')
})
