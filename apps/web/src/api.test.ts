import { afterEach, describe, expect, it, vi } from 'vitest'

import type { LibraryId, SourceId } from '@loredock/contracts'

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

  it('accepts an empty 204 response when deleting a source', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(coreApi.deleteSource('source-id' as SourceId)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/sources/source-id', { method: 'DELETE' })
  })
})
