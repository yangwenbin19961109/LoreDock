import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ImportBatchId, JobId, LibraryId, SourceId } from '@loredock/contracts'

import { coreApi } from './api'
import type { CoreApiError } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LoreDock Core API client', () => {
  it('uses the versioned endpoint when listing libraries', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], page: { limit: 50 } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(coreApi.listLibraries()).resolves.toEqual({ items: [], page: { limit: 50 } })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/libraries', { signal: undefined })
  })

  it('persists application settings through Core', async () => {
    const payload = {
      onboarding_completed: true,
      theme: 'dark' as const,
      default_search_mode: 'hybrid' as const
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...payload, updated_at: '2026-09-03T00:00:00Z' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.updateSettings(payload)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/settings',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify(payload) })
    )
  })

  it('reads the managed model state', async () => {
    const payload = {
      model_id: 'intfloat/multilingual-e5-small',
      display_name: '多语言快速模型',
      state: 'missing',
      active: false,
      restart_required: false,
      download_size_bytes: 1,
      required_space_bytes: 2,
      free_space_bytes: 3,
      error: null
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(coreApi.getDefaultModel()).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/models/default', { signal: undefined })
  })

  it('starts a persistent model install job', async () => {
    const job = {
      id: 'model-job',
      model_id: 'intfloat/multilingual-e5-small',
      status: 'pending',
      attempts: 0,
      bytes_downloaded: 0,
      bytes_total: 100,
      current_file: null,
      error: null,
      created_at: '2026-09-03T00:00:00Z',
      updated_at: '2026-09-03T00:00:00Z'
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(job), {
        status: 202,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(coreApi.installDefaultModel()).resolves.toEqual(job)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/models/default/install', { method: 'POST' })
  })

  it('surfaces the Core error message', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ error: { code: 'library_name_conflict', message: '名称已存在。' } }),
            { status: 409, headers: { 'Content-Type': 'application/json' } }
          )
        )
    )

    const request = coreApi.createLibrary('重复名称')
    await expect(request).rejects.toEqual(
      expect.objectContaining<Partial<CoreApiError>>({
        message: '名称已存在。',
        status: 409
      })
    )
  })

  it('passes bounded source pagination options to Core', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], page: { limit: 10, next_cursor: null } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.listSources('library-id' as LibraryId, {
      limit: 10,
      cursor: 'next page',
      filter: 'PDF 文档',
      sort: 'name-asc'
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/libraries/library-id/sources?limit=10&cursor=next+page&filter=PDF+%E6%96%87%E6%A1%A3&sort=name-asc',
      { signal: undefined }
    )
  })

  it('posts a URL for a bounded web snapshot', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ source: {}, job: {}, duplicate: false }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.importUrl('library-id' as LibraryId, 'https://example.com/guide')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/libraries/library-id/url-sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: 'https://example.com/guide' })
    })
  })

  it('forwards cancellation to a source upload', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ source: {}, job: {}, duplicate: false }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    const file = new File(['正文'], 'note.md', { type: 'text/markdown' })

    await coreApi.importSource('library-id' as LibraryId, file, controller.signal)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/libraries/library-id/sources',
      expect.objectContaining({ method: 'POST', signal: controller.signal })
    )
  })

  it('posts a bounded lexical search request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.search('library-id' as LibraryId, {
      query: '如何恢复任务？',
      limit: 8,
      lexical_only: true
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/libraries/library-id/search',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ query: '如何恢复任务？', limit: 8, lexical_only: true })
      })
    )
  })

  it('reads source content through the versioned API', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ source_id: 'source-id', text: '正文', char_start: 0, char_end: 2 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.readSource('source-id' as SourceId)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/sources/source-id/content', {
      signal: undefined
    })
  })

  it('requests a bounded source window for a search-result preview', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          source_id: 'source-id',
          text: '命中正文',
          char_start: 8000,
          char_end: 8004
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      )
    )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.readSource('source-id' as SourceId, undefined, { start: 8000, end: 14000 })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/sources/source-id/content?start=8000&end=14000',
      { signal: undefined }
    )
  })

  it('accepts an empty 204 response when deleting a source', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(coreApi.deleteSource('source-id' as SourceId)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/sources/source-id', { method: 'DELETE' })
  })

  it('cancels a queued source job through the versioned API', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'job-id', status: 'canceled' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.cancelJob('job-id' as JobId)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/jobs/job-id/cancel', { method: 'POST' })
  })

  it('creates and pauses a persistent import batch', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ id: 'batch-id', status: 'paused' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    )
    vi.stubGlobal('fetch', fetchMock)

    await coreApi.createImportBatch('library-id' as LibraryId, '资料批次', 3)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/libraries/library-id/import-batches',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: '资料批次', expected_items: 3 })
      })
    )

    await coreApi.pauseImportBatch('batch-id' as ImportBatchId)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/import-batches/batch-id/pause', {
      method: 'POST'
    })
  })
})
