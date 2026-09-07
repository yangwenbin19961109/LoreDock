import {
  type AppSettings,
  type AppSettingsUpdate,
  coreEndpoint,
  type ErrorResponse,
  type HealthResponse,
  type Job,
  type JobId,
  type Library,
  type LibraryCreateRequest,
  type LibraryId,
  type ModelStatus,
  type ModelJob,
  type Page,
  type SearchRequest,
  type SearchResponse,
  type Source,
  type SourceContentResponse,
  type SourceId,
  type SourceImportResponse
} from '@loredock/contracts'

import { coreConnection } from './runtime'

export class CoreApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message)
    this.name = 'CoreApiError'
  }
}

export interface SourceListOptions {
  readonly limit?: number
  readonly cursor?: string
  readonly filter?: string
  readonly sort?: 'updated-desc' | 'name-asc' | 'size-desc'
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const connection = await coreConnection()
  const endpoint = `${connection?.baseUrl ?? ''}${coreEndpoint(path)}`
  let requestInit = init
  if (connection) {
    const headers = new Headers(init?.headers)
    headers.set('Authorization', `Bearer ${connection.token}`)
    requestInit = { ...init, headers }
  }
  const response = await fetch(endpoint, requestInit)
  if (!response.ok) {
    let message = `LoreDock Core 请求失败（${response.status}）`
    try {
      const payload = (await response.json()) as ErrorResponse
      message = payload.error.message
    } catch {
      // Some proxy and transport errors do not use the Core error envelope.
    }
    throw new CoreApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const coreApi = {
  getSettings(signal?: AbortSignal): Promise<AppSettings> {
    return request<AppSettings>('settings', { signal })
  },

  updateSettings(payload: AppSettingsUpdate): Promise<AppSettings> {
    return request<AppSettings>('settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
  },

  getDefaultModel(signal?: AbortSignal): Promise<ModelStatus> {
    return request<ModelStatus>('models/default', { signal })
  },

  latestModelJob(signal?: AbortSignal): Promise<ModelJob | null> {
    return request<ModelJob | null>('models/jobs/latest', { signal })
  },

  installDefaultModel(): Promise<ModelJob> {
    return request<ModelJob>('models/default/install', { method: 'POST' })
  },

  getModelJob(jobId: string): Promise<ModelJob> {
    return request<ModelJob>(`models/jobs/${jobId}`)
  },

  retryModelJob(jobId: string): Promise<ModelJob> {
    return request<ModelJob>(`models/jobs/${jobId}/retry`, { method: 'POST' })
  },

  cancelModelJob(jobId: string): Promise<ModelJob> {
    return request<ModelJob>(`models/jobs/${jobId}/cancel`, { method: 'POST' })
  },

  health(signal?: AbortSignal): Promise<HealthResponse> {
    return request<HealthResponse>('health', { signal })
  },

  listLibraries(signal?: AbortSignal): Promise<Page<Library>> {
    return request<Page<Library>>('libraries', { signal })
  },

  createLibrary(name: string): Promise<Library> {
    const payload: LibraryCreateRequest = { name }
    return request<Library>('libraries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
  },

  renameLibrary(libraryId: LibraryId, name: string): Promise<Library> {
    const payload: LibraryCreateRequest = { name }
    return request<Library>(`libraries/${libraryId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
  },

  deleteLibrary(libraryId: LibraryId): Promise<void> {
    return request<void>(`libraries/${libraryId}`, { method: 'DELETE' })
  },

  listSources(
    libraryId: LibraryId,
    options: SourceListOptions = {},
    signal?: AbortSignal
  ): Promise<Page<Source>> {
    const parameters = new URLSearchParams()
    if (options.limit !== undefined) parameters.set('limit', String(options.limit))
    if (options.cursor) parameters.set('cursor', options.cursor)
    if (options.filter) parameters.set('filter', options.filter)
    if (options.sort) parameters.set('sort', options.sort)
    const query = parameters.size > 0 ? `?${parameters.toString()}` : ''
    return request<Page<Source>>(`libraries/${libraryId}/sources${query}`, { signal })
  },

  importSource(
    libraryId: LibraryId,
    file: File,
    signal?: AbortSignal
  ): Promise<SourceImportResponse> {
    const body = new FormData()
    body.append('file', file)
    return request<SourceImportResponse>(`libraries/${libraryId}/sources`, {
      method: 'POST',
      body,
      signal
    })
  },

  importUrl(libraryId: LibraryId, url: string): Promise<SourceImportResponse> {
    return request<SourceImportResponse>(`libraries/${libraryId}/url-sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    })
  },

  search(libraryId: LibraryId, payload: SearchRequest): Promise<SearchResponse> {
    return request<SearchResponse>(`libraries/${libraryId}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
  },

  readSource(
    sourceId: Source['id'],
    signal?: AbortSignal,
    range?: { readonly start: number; readonly end: number }
  ): Promise<SourceContentResponse> {
    const query = range
      ? `?${new URLSearchParams({ start: String(range.start), end: String(range.end) })}`
      : ''
    return request<SourceContentResponse>(`sources/${sourceId}/content${query}`, { signal })
  },

  deleteSource(sourceId: SourceId): Promise<void> {
    return request<void>(`sources/${sourceId}`, { method: 'DELETE' })
  },

  getJob(jobId: JobId): Promise<Job> {
    return request<Job>(`jobs/${jobId}`)
  },

  retryJob(jobId: JobId): Promise<Job> {
    return request<Job>(`jobs/${jobId}/retry`, { method: 'POST' })
  }
}
