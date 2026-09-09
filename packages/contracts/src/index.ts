export const API_VERSION = 'v1' as const
export const CORE_VERSION = '0.1.0' as const

export type ApiVersion = typeof API_VERSION

export interface HealthResponse {
  readonly status: 'ok'
  readonly service: 'loredock-core'
  readonly version: string
  readonly api_version: ApiVersion
}

export interface VersionResponse {
  readonly product: 'LoreDock'
  readonly core_version: string
  readonly api_version: ApiVersion
}

export type ThemePreference = 'system' | 'light' | 'dark'
export type DefaultSearchMode = 'hybrid' | 'lexical'

export interface AppSettings {
  readonly onboarding_completed: boolean
  readonly theme: ThemePreference
  readonly default_search_mode: DefaultSearchMode
  readonly updated_at: string
}

export interface AppSettingsUpdate {
  readonly onboarding_completed: boolean
  readonly theme: ThemePreference
  readonly default_search_mode: DefaultSearchMode
}

export interface ModelStatus {
  readonly model_id: string
  readonly display_name: string
  readonly state: 'missing' | 'ready' | 'corrupt'
  readonly active: boolean
  readonly restart_required: boolean
  readonly download_size_bytes: number
  readonly required_space_bytes: number
  readonly free_space_bytes: number
  readonly error: string | null
}

export interface ModelJob {
  readonly id: string
  readonly model_id: string
  readonly status: 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'
  readonly attempts: number
  readonly bytes_downloaded: number
  readonly bytes_total: number
  readonly current_file: string | null
  readonly error: string | null
  readonly created_at: string
  readonly updated_at: string
}

export interface ErrorDetail {
  readonly code: string
  readonly message: string
  readonly request_id?: string
  readonly fields?: Readonly<Record<string, readonly string[]>>
}

export interface ErrorResponse {
  readonly error: ErrorDetail
}

export interface PageInfo {
  readonly limit: number
  readonly next_cursor?: string | null
}

export interface Page<T> {
  readonly items: readonly T[]
  readonly page: PageInfo
}

export type LibraryId = string & { readonly __brand: 'LibraryId' }
export type SourceId = string & { readonly __brand: 'SourceId' }
export type ChunkId = string & { readonly __brand: 'ChunkId' }
export type JobId = string & { readonly __brand: 'JobId' }
export type ImportBatchId = string & { readonly __brand: 'ImportBatchId' }

export interface Library {
  readonly id: LibraryId
  readonly name: string
  readonly created_at: string
  readonly updated_at: string
}

export interface Source {
  readonly id: SourceId
  readonly library_id: LibraryId
  readonly name: string
  readonly media_type: string
  readonly status: string
  readonly content_hash: string
  readonly size_bytes: number
  readonly source_kind?: 'file' | 'url'
  readonly origin_url?: string | null
  readonly error: string | null
  readonly created_at: string
  readonly updated_at: string
}

export interface Job {
  readonly id: JobId
  readonly library_id: LibraryId
  readonly source_id: SourceId | null
  readonly batch_id?: ImportBatchId | null
  readonly kind: string
  readonly status: string
  readonly attempts: number
  readonly progress: number
  readonly error: string | null
  readonly created_at: string
  readonly updated_at: string
}

export interface SourceImportResponse {
  readonly source: Source
  readonly job: Job
  readonly duplicate: boolean
}

export interface ImportBatch {
  readonly id: ImportBatchId
  readonly library_id: LibraryId
  readonly name: string
  readonly status:
    'uploading' | 'processing' | 'paused' | 'succeeded' | 'partial' | 'failed' | 'canceled'
  readonly expected_items: number
  readonly job_count: number
  readonly completed_items: number
  readonly succeeded_items: number
  readonly duplicate_items: number
  readonly failed_items: number
  readonly canceled_items: number
  readonly created_at: string
  readonly updated_at: string
}

export interface LibraryCreateRequest {
  readonly name: string
}

export interface SearchResult {
  readonly chunk_id: ChunkId
  readonly source_id: SourceId
  readonly text: string
  readonly score: number
  readonly char_start: number
  readonly char_end: number
  readonly page: number | null
  readonly title_path: readonly string[]
  readonly matched_chunk_id: ChunkId
  readonly parent_id: string | null
  readonly context_id: string
  readonly context_text: string
  readonly matched_range: CitationRange
  readonly context_range: CitationRange
}

export interface CitationRange {
  readonly char_start: number
  readonly char_end: number
  readonly page_start: number | null
  readonly page_end: number | null
}

export interface SearchRequest {
  readonly query: string
  readonly limit?: number
  readonly lexical_only?: boolean
}

export interface SearchResponse {
  readonly items: readonly SearchResult[]
}

export interface SourceContentResponse {
  readonly source_id: SourceId
  readonly text: string
  readonly char_start: number
  readonly char_end: number
}

export const coreEndpoint = (path: string): string =>
  `/api/${API_VERSION}/${path.replace(/^\//, '')}`
