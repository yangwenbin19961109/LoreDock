import type { DragEvent, FormEvent } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type {
  AppSettings,
  CitationRange,
  Job,
  Library,
  LibraryId,
  ModelStatus,
  ModelJob,
  SearchResult,
  Source,
  SourceContentResponse,
  SourceId,
  SourceImportResponse
} from '@loredock/contracts'
import { Button } from '@loredock/ui'

import { coreApi } from './api'
import type { SourceListOptions } from './api'
import { DocumentPreview } from './documentPreview'
import { AgentConnections } from './AgentConnections'
import { SourceCollection } from './SourceCollection'
import { FavoriteButton } from './FavoriteButton'
import { activityApi, type CollectionKind } from './activityApi'
import { desktopCoreStatus, restartDesktopCore, type DesktopCoreStatus } from './runtime'
import { planFolderImport, type FolderImportPlan } from './folderImport'

type CoreState = 'checking' | 'ready' | 'recovering' | 'failed' | 'offline'
type DetailTab = 'preview' | 'details'
type SourceSort = NonNullable<SourceListOptions['sort']>

interface ImportProgressState {
  readonly total: number
  readonly completed: number
  readonly currentName: string
  readonly status: 'running' | 'succeeded' | 'partial' | 'failed' | 'canceled'
  readonly succeeded?: number
  readonly duplicates?: number
  readonly failed?: number
  readonly skipped?: number
}

const SOURCE_PAGE_SIZE = 10
type DeleteTarget =
  | { readonly kind: 'library'; readonly id: LibraryId; readonly name: string }
  | { readonly kind: 'source'; readonly id: SourceId; readonly name: string }

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}

function sourceStatus(status: string): string {
  const labels: Record<string, string> = {
    pending: '等待处理',
    parsing: '正在解析',
    chunking: '正在分块',
    embedding: '正在索引',
    succeeded: '可以搜索',
    ready: '可以搜索',
    failed: '处理失败'
  }
  return labels[status] ?? status
}

export function App() {
  const [coreState, setCoreState] = useState<CoreState>('checking')
  const [coreVersion, setCoreVersion] = useState<string>()
  const [coreDiagnostic, setCoreDiagnostic] = useState<DesktopCoreStatus>()
  const [libraries, setLibraries] = useState<readonly Library[]>([])
  const [selectedId, setSelectedId] = useState<LibraryId>()
  const [sources, setSources] = useState<readonly Source[]>([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [sourceSort, setSourceSort] = useState<SourceSort>('updated-desc')
  const [sourceCursor, setSourceCursor] = useState<string>()
  const [sourceListRevision, setSourceListRevision] = useState(0)
  const [sourceCursorHistory, setSourceCursorHistory] = useState<readonly string[]>([])
  const [nextSourceCursor, setNextSourceCursor] = useState<string>()
  const [jobs, setJobs] = useState<Readonly<Record<string, Job>>>({})
  const [selectedSourceId, setSelectedSourceId] = useState<SourceId>()
  const [sourceContent, setSourceContent] = useState<SourceContentResponse>()
  const [highlightRange, setHighlightRange] = useState<CitationRange>()
  const [previewRequestRevision, setPreviewRequestRevision] = useState(0)
  const [detailTab, setDetailTab] = useState<DetailTab>('preview')
  const [showCreate, setShowCreate] = useState(false)
  const [showUrlImport, setShowUrlImport] = useState(false)
  const [folderPlan, setFolderPlan] = useState<FolderImportPlan>()
  const [folderRetryPlan, setFolderRetryPlan] = useState<FolderImportPlan>()
  const [showRename, setShowRename] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showAgents, setShowAgents] = useState(false)
  const [collection, setCollection] = useState<CollectionKind>()
  const [settings, setSettings] = useState<AppSettings>()
  const [modelStatus, setModelStatus] = useState<ModelStatus>()
  const [modelJob, setModelJob] = useState<ModelJob | null>(null)
  const [libraryName, setLibraryName] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [renameName, setRenameName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>()
  const [busy, setBusy] = useState(false)
  const [importProgress, setImportProgress] = useState<ImportProgressState>()
  const [query, setQuery] = useState('')
  const [lexicalOnly, setLexicalOnly] = useState(false)
  const [searching, setSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [results, setResults] = useState<readonly SearchResult[]>([])
  const [expandedContexts, setExpandedContexts] = useState<ReadonlySet<string>>(new Set())
  const [draggingFiles, setDraggingFiles] = useState(false)
  const [error, setError] = useState<string>()
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const folderImportController = useRef<AbortController | undefined>(undefined)
  const dragDepth = useRef(0)
  const previousDesktopCoreState = useRef<string | undefined>(undefined)

  const selectedLibrary = libraries.find((library) => library.id === selectedId)
  const selectedSource = sources.find((source) => source.id === selectedSourceId)
  const sourcePage = sourceCursorHistory.length + 1
  const activeModelJobId =
    modelJob && ['pending', 'running'].includes(modelJob.status) ? modelJob.id : undefined
  const activeJobs = useMemo(
    () => Object.values(jobs).filter((job) => !['succeeded', 'failed'].includes(job.status)),
    [jobs]
  )

  useEffect(() => {
    const controller = new AbortController()
    void desktopCoreStatus()
      .then((status) => {
        if (status && status.state !== 'ready') {
          setCoreDiagnostic(status)
          setCoreState(
            status.state === 'recovering'
              ? 'recovering'
              : status.state === 'failed'
                ? 'failed'
                : 'checking'
          )
          previousDesktopCoreState.current = status.state
          return undefined
        }
        return Promise.all([
          coreApi.health(controller.signal),
          coreApi.listLibraries(controller.signal),
          coreApi.getSettings(controller.signal),
          coreApi.getDefaultModel(controller.signal),
          coreApi.latestModelJob(controller.signal)
        ])
      })
      .then((result) => {
        if (!result) return
        const [health, page, loadedSettings, loadedModel, loadedModelJob] = result
        setCoreVersion(health.version)
        setLibraries(page.items)
        setSelectedId(page.items[0]?.id)
        setSettings(loadedSettings)
        setModelStatus(loadedModel)
        setModelJob(loadedModelJob)
        setLexicalOnly(loadedSettings.default_search_mode === 'lexical')
        setCoreState('ready')
        previousDesktopCoreState.current = 'ready'
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setCoreState('offline')
        setError('无法连接 LoreDock Core，请确认核心服务已经启动。')
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    let disposed = false
    async function synchronizeDesktopCore(): Promise<void> {
      try {
        const status = await desktopCoreStatus()
        if (!status || disposed) return
        const previous = previousDesktopCoreState.current
        setCoreDiagnostic(status)
        if (status.state === 'ready') {
          setCoreState('ready')
          if (previous !== 'ready') {
            const [health, page, loadedSettings, loadedModel, loadedModelJob] = await Promise.all([
              coreApi.health(),
              coreApi.listLibraries(),
              coreApi.getSettings(),
              coreApi.getDefaultModel(),
              coreApi.latestModelJob()
            ])
            if (disposed) return
            setCoreVersion(health.version)
            setLibraries(page.items)
            setSettings(loadedSettings)
            setModelStatus(loadedModel)
            setModelJob(loadedModelJob)
            setLexicalOnly(loadedSettings.default_search_mode === 'lexical')
            previousDesktopCoreState.current = 'ready'
            setSelectedId((current) =>
              current && page.items.some((library) => library.id === current)
                ? current
                : page.items[0]?.id
            )
            setError(undefined)
          }
        } else if (status.state === 'recovering') {
          previousDesktopCoreState.current = status.state
          setCoreState('recovering')
        } else if (status.state === 'failed') {
          previousDesktopCoreState.current = status.state
          setCoreState('failed')
        } else {
          previousDesktopCoreState.current = status.state
          setCoreState('checking')
        }
      } catch (reason) {
        if (!disposed) {
          previousDesktopCoreState.current = undefined
          setError(
            reason instanceof TypeError
              ? 'Core 已启动，但数据连接暂时不可用，正在自动重试。'
              : reason instanceof Error
                ? reason.message
                : '无法读取 Core 运行状态。'
          )
        }
      }
    }
    void synchronizeDesktopCore()
    const timer = window.setInterval(() => void synchronizeDesktopCore(), 1000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    const theme = settings?.theme ?? 'system'
    document.documentElement.dataset.theme = theme
    return () => {
      delete document.documentElement.dataset.theme
    }
  }, [settings?.theme])

  useEffect(() => {
    if (!activeModelJobId) return
    let disposed = false
    const timer = window.setInterval(() => {
      void coreApi
        .getModelJob(activeModelJobId)
        .then(async (job) => {
          if (disposed) return
          setModelJob(job)
          if (job.status === 'succeeded') setModelStatus(await coreApi.getDefaultModel())
        })
        .catch((reason: unknown) => {
          if (!disposed) setError(reason instanceof Error ? reason.message : '模型进度读取失败。')
        })
    }, 500)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [activeModelJobId])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    void coreApi
      .listSources(
        selectedId,
        {
          limit: SOURCE_PAGE_SIZE,
          sort: sourceSort,
          ...(sourceCursor ? { cursor: sourceCursor } : {}),
          ...(sourceFilter.trim() ? { filter: sourceFilter.trim() } : {})
        },
        controller.signal
      )
      .then((page) => {
        setSources(page.items)
        setNextSourceCursor(page.page.next_cursor ?? undefined)
        setSelectedSourceId(page.items[0]?.id)
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof Error ? reason.message : '资料列表加载失败。')
      })
    return () => controller.abort()
  }, [selectedId, sourceCursor, sourceFilter, sourceSort, sourceListRevision])

  useEffect(() => {
    if (!selectedSourceId) return
    const controller = new AbortController()
    let disposed = false
    const previewRange = highlightRange
      ? {
          start: Math.max(0, highlightRange.char_start - 2000),
          end: Math.max(highlightRange.char_end + 2000, highlightRange.char_start + 6000)
        }
      : undefined
    void coreApi
      .readSource(selectedSourceId, controller.signal, previewRange)
      .then((content) => {
        if (!disposed) setSourceContent(content)
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        if (!disposed) setError(reason instanceof Error ? reason.message : '原文读取失败。')
      })
    return () => {
      disposed = true
      controller.abort()
    }
  }, [highlightRange, previewRequestRevision, selectedSourceId])

  useEffect(() => {
    if (activeJobs.length === 0) return
    const timer = window.setInterval(() => {
      void Promise.all(activeJobs.map((job) => coreApi.getJob(job.id))).then((updated) => {
        setJobs((current) => {
          const next = { ...current }
          for (const job of updated) {
            if (job.source_id) next[job.source_id] = job
          }
          return next
        })
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [activeJobs])

  function resetSelection(): void {
    setSelectedSourceId(undefined)
    setSourceContent(undefined)
    setHighlightRange(undefined)
    setDetailTab('preview')
    setQuery('')
    setResults([])
    setHasSearched(false)
    setExpandedContexts(new Set())
  }

  function selectLibrary(libraryId: LibraryId): void {
    setCollection(undefined)
    setShowAgents(false)
    resetSelection()
    setSources([])
    setSourceFilter('')
    setSourceSort('updated-desc')
    setSourceCursor(undefined)
    setSourceCursorHistory([])
    setNextSourceCursor(undefined)
    setSelectedId(libraryId)
    // Returning to the already-active library must reload after another view cleared the list.
    setSourceListRevision((revision) => revision + 1)
  }

  function selectSource(sourceId: SourceId, range?: CitationRange): void {
    setSelectedSourceId(sourceId)
    // Do not let a new citation try to scroll within the stale window from the same source.
    setSourceContent(undefined)
    setHighlightRange(range)
    setPreviewRequestRevision((revision) => revision + 1)
    setDetailTab('preview')
  }

  function openSourceByUser(sourceId: SourceId, range?: CitationRange): void {
    selectSource(sourceId, range)
    void activityApi
      .visit(sourceId)
      .catch(() => setError('最近使用记录未保存，请确认 Core 已更新并在线。'))
  }

  function resetSearch(): void {
    setQuery('')
    setResults([])
    setHasSearched(false)
    setExpandedContexts(new Set())
    setHighlightRange(undefined)
  }

  function enterFileDrop(event: DragEvent<HTMLElement>): void {
    event.preventDefault()
    if (!event.dataTransfer.types.includes('Files')) return
    dragDepth.current += 1
    setDraggingFiles(true)
  }

  function leaveFileDrop(event: DragEvent<HTMLElement>): void {
    event.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setDraggingFiles(false)
  }

  function finishFileDrop(event: DragEvent<HTMLElement>): void {
    event.preventDefault()
    dragDepth.current = 0
    setDraggingFiles(false)
    if (!busy) void importFiles(event.dataTransfer.files)
  }

  async function createLibrary(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const name = libraryName.trim()
    if (!name) return
    setBusy(true)
    setError(undefined)
    try {
      const library = await coreApi.createLibrary(name)
      setLibraries((current) => [...current, library])
      selectLibrary(library.id)
      setLibraryName('')
      setShowCreate(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '知识库创建失败。')
    } finally {
      setBusy(false)
    }
  }

  async function renameLibrary(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const name = renameName.trim()
    if (!selectedId || !name) return
    setBusy(true)
    setError(undefined)
    try {
      const updated = await coreApi.renameLibrary(selectedId, name)
      setLibraries((current) =>
        current.map((library) => (library.id === updated.id ? updated : library))
      )
      setShowRename(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '知识库重命名失败。')
    } finally {
      setBusy(false)
    }
  }

  async function confirmDelete(): Promise<void> {
    if (!deleteTarget) return
    setBusy(true)
    setError(undefined)
    try {
      if (deleteTarget.kind === 'library') {
        await coreApi.deleteLibrary(deleteTarget.id)
        const remaining = libraries.filter((library) => library.id !== deleteTarget.id)
        setLibraries(remaining)
        resetSelection()
        setSources([])
        setSelectedId(remaining[0]?.id)
      } else {
        await coreApi.deleteSource(deleteTarget.id)
        const remaining = sources.filter((source) => source.id !== deleteTarget.id)
        setSources(remaining)
        setSourceCursor(undefined)
        setSourceCursorHistory([])
        setResults((current) => current.filter((result) => result.source_id !== deleteTarget.id))
        setJobs((current) => {
          const next = { ...current }
          delete next[deleteTarget.id]
          return next
        })
        if (selectedSourceId === deleteTarget.id) {
          setSelectedSourceId(undefined)
          setSourceContent(undefined)
          setHighlightRange(undefined)
          if (remaining[0]) selectSource(remaining[0].id)
        }
      }
      setDeleteTarget(undefined)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除失败。')
    } finally {
      setBusy(false)
    }
  }

  async function importFiles(files: FileList | null): Promise<void> {
    if (!selectedId || !files?.length) return
    const selectedFiles = Array.from(files)
    setBusy(true)
    setError(undefined)
    setImportProgress({
      total: selectedFiles.length,
      completed: 0,
      currentName: selectedFiles[0]?.name ?? '',
      status: 'running'
    })
    try {
      const imported: SourceImportResponse[] = []
      for (const [index, file] of selectedFiles.entries()) {
        setImportProgress({
          total: selectedFiles.length,
          completed: index,
          currentName: file.name,
          status: 'running'
        })
        imported.push(await coreApi.importSource(selectedId, file))
        setImportProgress({
          total: selectedFiles.length,
          completed: index + 1,
          currentName: file.name,
          status: index + 1 === selectedFiles.length ? 'succeeded' : 'running'
        })
      }
      setJobs((current) => {
        const next = { ...current }
        for (const item of imported) next[item.source.id] = item.job
        return next
      })
      const page = await coreApi.listSources(selectedId, { limit: SOURCE_PAGE_SIZE })
      setSources(page.items)
      setSourceFilter('')
      setSourceSort('updated-desc')
      setSourceCursor(undefined)
      setSourceCursorHistory([])
      setNextSourceCursor(page.page.next_cursor ?? undefined)
      const firstSourceId = imported[0]?.source.id ?? page.items[0]?.id
      if (firstSourceId) selectSource(firstSourceId)
    } catch (reason) {
      setImportProgress((current) => (current ? { ...current, status: 'failed' } : current))
      setError(reason instanceof Error ? reason.message : '资料导入失败。')
    } finally {
      setBusy(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  function prepareFolderImport(files: FileList | null): void {
    if (!files?.length) return
    setError(undefined)
    setFolderPlan(planFolderImport(Array.from(files)))
    if (folderInput.current) folderInput.current.value = ''
  }

  function cancelFolderImport(): void {
    folderImportController.current?.abort()
  }

  async function importFolder(planOverride?: FolderImportPlan): Promise<void> {
    const plan = planOverride ?? folderPlan
    if (!selectedId || !plan || plan.blockedReason || plan.files.length === 0) return
    const controller = new AbortController()
    folderImportController.current = controller
    setFolderPlan(undefined)
    setFolderRetryPlan(undefined)
    setBusy(true)
    setError(undefined)
    let succeeded = 0
    let duplicates = 0
    let failed = 0
    const imported: SourceImportResponse[] = []
    const failedFiles: FolderImportPlan['files'][number][] = []
    setImportProgress({
      total: plan.files.length,
      completed: 0,
      currentName: plan.files[0]?.relativePath ?? plan.folderName,
      status: 'running',
      skipped: plan.skipped.length
    })

    for (const [index, item] of plan.files.entries()) {
      if (controller.signal.aborted) break
      setImportProgress({
        total: plan.files.length,
        completed: index,
        currentName: item.relativePath,
        status: 'running',
        succeeded,
        duplicates,
        failed,
        skipped: plan.skipped.length
      })
      try {
        const result = await coreApi.importSource(selectedId, item.file, controller.signal)
        imported.push(result)
        if (result.duplicate) duplicates += 1
        else succeeded += 1
      } catch {
        if (controller.signal.aborted) break
        failed += 1
        failedFiles.push(item)
      }
      setImportProgress({
        total: plan.files.length,
        completed: index + 1,
        currentName: item.relativePath,
        status: 'running',
        succeeded,
        duplicates,
        failed,
        skipped: plan.skipped.length
      })
    }

    const canceled = controller.signal.aborted
    const completed = succeeded + duplicates + failed
    const remainingFiles = canceled ? plan.files.slice(completed) : []
    const retryFiles = [...failedFiles, ...remainingFiles]
    if (retryFiles.length > 0) {
      setFolderRetryPlan({
        folderName: plan.folderName,
        files: retryFiles,
        skipped: [],
        totalBytes: retryFiles.reduce((sum, item) => sum + item.file.size, 0)
      })
    }
    const finalStatus = canceled
      ? 'canceled'
      : failed > 0
        ? succeeded + duplicates > 0
          ? 'partial'
          : 'failed'
        : 'succeeded'
    setImportProgress({
      total: plan.files.length,
      completed,
      currentName: plan.folderName,
      status: finalStatus,
      succeeded,
      duplicates,
      failed,
      skipped: plan.skipped.length
    })
    folderImportController.current = undefined

    try {
      if (imported.length > 0) {
        setJobs((current) => {
          const next = { ...current }
          for (const item of imported) next[item.source.id] = item.job
          return next
        })
      }
      const page = await coreApi.listSources(selectedId, { limit: SOURCE_PAGE_SIZE })
      setSources(page.items)
      setSourceFilter('')
      setSourceSort('updated-desc')
      setSourceCursor(undefined)
      setSourceCursorHistory([])
      setNextSourceCursor(page.page.next_cursor ?? undefined)
      const firstSourceId = imported[0]?.source.id ?? page.items[0]?.id
      if (firstSourceId) selectSource(firstSourceId)
      if (failed > 0) {
        setError(`${failed} 份资料导入失败，其余资料已保留。可以检查文件后单独重试。`)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '资料列表刷新失败。')
    } finally {
      setBusy(false)
    }
  }

  async function importUrl(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const url = sourceUrl.trim()
    if (!selectedId || !url) return
    setBusy(true)
    setError(undefined)
    setImportProgress({ total: 1, completed: 0, currentName: url, status: 'running' })
    try {
      const imported = await coreApi.importUrl(selectedId, url)
      setJobs((current) => ({ ...current, [imported.source.id]: imported.job }))
      const page = await coreApi.listSources(selectedId, { limit: SOURCE_PAGE_SIZE })
      setSources(page.items)
      setSourceFilter('')
      setSourceSort('updated-desc')
      setSourceCursor(undefined)
      setSourceCursorHistory([])
      setNextSourceCursor(page.page.next_cursor ?? undefined)
      setImportProgress({
        total: 1,
        completed: 1,
        currentName: imported.source.name,
        status: 'succeeded'
      })
      setSourceUrl('')
      setShowUrlImport(false)
      selectSource(imported.source.id)
    } catch (reason) {
      setImportProgress((current) => (current ? { ...current, status: 'failed' } : current))
      setError(reason instanceof Error ? reason.message : '网页导入失败。')
    } finally {
      setBusy(false)
    }
  }

  async function search(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const normalizedQuery = query.trim()
    if (!selectedId || !normalizedQuery) return
    setSearching(true)
    setError(undefined)
    try {
      const response = await coreApi.search(selectedId, {
        query: normalizedQuery,
        limit: 8,
        lexical_only: lexicalOnly
      })
      setResults(response.items)
      setExpandedContexts(new Set())
      setHasSearched(true)
      if (response.items[0])
        selectSource(response.items[0].source_id, response.items[0].matched_range)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '搜索失败。')
    } finally {
      setSearching(false)
    }
  }

  async function retrySource(sourceId: SourceId): Promise<void> {
    const job = jobs[sourceId]
    if (!job) return
    setError(undefined)
    try {
      const updated = await coreApi.retryJob(job.id)
      setJobs((current) => ({ ...current, [sourceId]: updated }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '任务重试失败。')
    }
  }

  function toggleContext(contextId: string): void {
    setExpandedContexts((current) => {
      const next = new Set(current)
      if (next.has(contextId)) next.delete(contextId)
      else next.add(contextId)
      return next
    })
  }

  async function restartCore(): Promise<void> {
    setCoreState('checking')
    setError(undefined)
    try {
      await restartDesktopCore()
    } catch (reason) {
      setCoreState('failed')
      setError(reason instanceof Error ? reason.message : 'Core 重启请求失败。')
    }
  }

  async function copyCoreDiagnostic(): Promise<void> {
    if (!coreDiagnostic) return
    const diagnostic = [
      `state=${coreDiagnostic.state}`,
      `error_code=${coreDiagnostic.errorCode ?? 'none'}`,
      `restart_count=${coreDiagnostic.restartCount}`,
      `message=${coreDiagnostic.message ?? 'none'}`
    ].join('\n')
    try {
      await navigator.clipboard.writeText(diagnostic)
    } catch {
      setError('无法复制诊断信息，请检查系统剪贴板权限。')
    }
  }

  async function saveSettings(next: {
    readonly onboarding_completed: boolean
    readonly theme: AppSettings['theme']
    readonly default_search_mode: AppSettings['default_search_mode']
  }): Promise<void> {
    setBusy(true)
    setError(undefined)
    try {
      const updated = await coreApi.updateSettings(next)
      setSettings(updated)
      setLexicalOnly(updated.default_search_mode === 'lexical')
      setShowSettings(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '设置保存失败。')
    } finally {
      setBusy(false)
    }
  }

  async function installModel(): Promise<void> {
    setError(undefined)
    try {
      setModelJob(await coreApi.installDefaultModel())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '模型安装失败。')
    }
  }

  async function cancelModel(): Promise<void> {
    if (!modelJob) return
    try {
      setModelJob(await coreApi.cancelModelJob(modelJob.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法取消模型下载。')
    }
  }

  async function retryModel(): Promise<void> {
    if (!modelJob) return
    try {
      setModelJob(await coreApi.retryModelJob(modelJob.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法重试模型下载。')
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <img className="brand-mark" src="/loredock-icon.png" alt="" />
          <strong>LoreDock</strong>
        </div>
        <nav className="main-nav" aria-label="主导航">
          <button
            className={`nav-item ${!showAgents && !collection ? 'nav-item--active' : ''}`}
            type="button"
            onClick={() => {
              setShowAgents(false)
              setCollection(undefined)
            }}
          >
            <span>▣</span>全部知识库
          </button>
          <button
            className={`nav-item ${collection === 'recent' ? 'nav-item--active' : ''}`}
            type="button"
            onClick={() => {
              setCollection('recent')
              setShowAgents(false)
            }}
          >
            <span aria-hidden="true">◷</span>最近使用
          </button>
          <button
            className={`nav-item ${collection === 'favorites' ? 'nav-item--active' : ''}`}
            type="button"
            onClick={() => {
              setCollection('favorites')
              setShowAgents(false)
            }}
          >
            <span aria-hidden="true">☆</span>收藏
          </button>
          <button
            className={`nav-item ${showAgents ? 'nav-item--active' : ''}`}
            type="button"
            onClick={() => {
              setShowAgents(true)
              setCollection(undefined)
            }}
          >
            <span>◎</span>Agent 连接
          </button>
          <button
            className="nav-item"
            type="button"
            onClick={() => setShowSettings(true)}
            disabled={!settings}
          >
            <span>⚙</span>设置
          </button>
        </nav>
        <div className="sidebar-heading">
          <span>我的知识库</span>
          <button
            className="icon-button"
            type="button"
            aria-label="创建知识库"
            onClick={() => setShowCreate(true)}
            disabled={coreState !== 'ready'}
          >
            +
          </button>
        </div>
        <nav className="library-list" aria-label="知识库列表">
          {libraries.map((library) => (
            <button
              className={`library-item ${library.id === selectedId ? 'library-item--active' : ''}`}
              type="button"
              key={library.id}
              onClick={() => {
                setShowAgents(false)
                selectLibrary(library.id)
              }}
            >
              <span className="library-glyph">▤</span>
              <span>
                <strong>{library.name}</strong>
                <small>{library.id === selectedId ? `${sources.length} 份资料` : '知识库'}</small>
              </span>
            </button>
          ))}
          {coreState === 'ready' && libraries.length === 0 && (
            <p className="sidebar-empty">还没有知识库</p>
          )}
        </nav>
        <div className={`core-status core-status--${coreState}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          {coreState === 'checking' && '正在连接 Core'}
          {coreState === 'ready' && `Core ${coreVersion ?? ''} 已连接`}
          {coreState === 'recovering' && `Core 正在恢复（${coreDiagnostic?.restartCount ?? 0}/3）`}
          {coreState === 'failed' && 'Core 启动失败'}
          {coreState === 'offline' && 'Core 未连接'}
        </div>
      </aside>

      {collection ? (
        <SourceCollection key={collection} kind={collection} libraries={libraries} />
      ) : showAgents ? (
        <AgentConnections libraries={libraries} />
      ) : (
        <section className="work-area">
          <header className="topbar">
            <div>
              <p className="eyebrow">知识库</p>
              <h1>{selectedLibrary?.name ?? '开始使用 LoreDock'}</h1>
            </div>
            <div className="topbar-actions">
              {selectedLibrary && (
                <>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setRenameName(selectedLibrary.name)
                      setShowRename(true)
                    }}
                    disabled={busy}
                  >
                    重命名
                  </Button>
                  <Button
                    variant="ghost"
                    className="danger-action"
                    onClick={() =>
                      setDeleteTarget({
                        kind: 'library',
                        id: selectedLibrary.id,
                        name: selectedLibrary.name
                      })
                    }
                    disabled={busy}
                  >
                    删除
                  </Button>
                </>
              )}
              <Button variant="secondary" onClick={() => setShowCreate(true)} disabled={busy}>
                创建知识库
              </Button>
            </div>
          </header>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button type="button" onClick={() => setError(undefined)} aria-label="关闭错误提示">
                ×
              </button>
            </div>
          )}
          {importProgress && (
            <section
              className={`import-progress import-progress--${importProgress.status}`}
              role="status"
              aria-live="polite"
              aria-label="资料导入进度"
            >
              <div className="import-progress-copy">
                <strong>
                  {importProgress.status === 'running'
                    ? `正在处理 ${importProgress.completed + 1}/${importProgress.total}`
                    : importProgress.status === 'succeeded'
                      ? `已完成 ${importProgress.completed}/${importProgress.total}`
                      : importProgress.status === 'partial'
                        ? `已处理 ${importProgress.completed}/${importProgress.total}`
                        : importProgress.status === 'canceled'
                          ? `已取消，完成 ${importProgress.completed}/${importProgress.total}`
                          : `导入失败 ${importProgress.completed}/${importProgress.total}`}
                </strong>
                <span title={importProgress.currentName}>
                  {importProgress.status === 'running'
                    ? importProgress.currentName
                    : importProgress.succeeded === undefined
                      ? importProgress.currentName
                      : `新增 ${importProgress.succeeded} · 已存在 ${importProgress.duplicates ?? 0} · 失败 ${importProgress.failed ?? 0} · 跳过 ${importProgress.skipped ?? 0}`}
                </span>
              </div>
              <progress
                {...(importProgress.status === 'running' && importProgress.total === 1
                  ? {}
                  : { value: importProgress.completed })}
                max={importProgress.total}
                aria-label={`已完成 ${importProgress.completed}，共 ${importProgress.total} 份资料`}
              />
              {importProgress.status === 'running' && folderImportController.current ? (
                <button type="button" onClick={cancelFolderImport} aria-label="取消文件夹导入">
                  停止
                </button>
              ) : importProgress.status !== 'running' ? (
                <div className="import-progress-actions">
                  {folderRetryPlan && (
                    <button type="button" onClick={() => void importFolder(folderRetryPlan)}>
                      {importProgress.status === 'canceled' ? '继续' : '重试'}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setImportProgress(undefined)
                      setFolderRetryPlan(undefined)
                    }}
                    aria-label="关闭导入进度"
                  >
                    ×
                  </button>
                </div>
              ) : null}
            </section>
          )}
          {(coreState === 'recovering' || coreState === 'failed') && coreDiagnostic && (
            <section className={`core-diagnostic core-diagnostic--${coreState}`} role="alert">
              <div>
                <strong>{coreState === 'recovering' ? '正在恢复 Core' : 'Core 无法启动'}</strong>
                <p>{coreDiagnostic.message ?? '桌面核心服务暂时不可用。'}</p>
                {coreDiagnostic.errorCode && <code>{coreDiagnostic.errorCode}</code>}
              </div>
              <div className="core-diagnostic-actions">
                <button type="button" onClick={() => void copyCoreDiagnostic()}>
                  复制诊断
                </button>
                {coreState === 'failed' && (
                  <button type="button" className="primary" onClick={() => void restartCore()}>
                    重新启动 Core
                  </button>
                )}
              </div>
            </section>
          )}

          {!selectedLibrary ? (
            <section className="empty-state">
              <div className="empty-symbol">◇</div>
              <h2>创建你的第一个知识库</h2>
              <p>
                把分散的 Markdown、TXT、PDF、DOCX、PPTX、XLSX 和 HTML
                资料集中管理，稍后即可搜索和连接 Agent。
              </p>
              <Button onClick={() => setShowCreate(true)} disabled={coreState !== 'ready'}>
                创建知识库
              </Button>
            </section>
          ) : (
            <div
              className={`workspace-grid ${draggingFiles ? 'workspace-grid--dragging' : ''}`}
              onDragEnter={enterFileDrop}
              onDragOver={(event) => {
                event.preventDefault()
                event.dataTransfer.dropEffect = 'copy'
              }}
              onDragLeave={leaveFileDrop}
              onDrop={finishFileDrop}
            >
              {draggingFiles && (
                <div className="drop-overlay" role="status" aria-live="polite">
                  <span className="drop-icon" aria-hidden="true">
                    ⇧
                  </span>
                  <strong>松开即可添加资料</strong>
                  <span>支持 Markdown、TXT、PDF、DOCX、PPTX、XLSX 和 HTML</span>
                </div>
              )}
              <section className="center-column">
                <form className="search-toolbar" onSubmit={(event) => void search(event)}>
                  <label className="visually-hidden" htmlFor="knowledge-query">
                    搜索问题
                  </label>
                  <span className="search-icon">⌕</span>
                  <input
                    id="knowledge-query"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索这个知识库"
                    maxLength={2000}
                  />
                  <label className="search-mode">
                    <input
                      type="checkbox"
                      checked={lexicalOnly}
                      onChange={(event) => setLexicalOnly(event.target.checked)}
                    />
                    仅全文
                  </label>
                  <Button type="submit" disabled={!query.trim() || searching}>
                    {searching ? '搜索中…' : '搜索'}
                  </Button>
                  {(hasSearched || query) && (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={resetSearch}
                      disabled={searching}
                    >
                      重置
                    </Button>
                  )}
                </form>
                {hasSearched && (
                  <section className="search-results" aria-label="搜索结果">
                    <div className="result-summary">
                      {results.length === 0 ? '没有找到相关内容' : `${results.length} 条相关内容`}
                    </div>
                    {results.map((result) => {
                      const source = sources.find((item) => item.id === result.source_id)
                      const expanded = expandedContexts.has(result.context_id)
                      const hasMore = result.context_text !== result.text
                      return (
                        <article
                          className="result-card"
                          key={`${result.matched_chunk_id}-${result.context_id}`}
                          onClick={() => openSourceByUser(result.source_id, result.matched_range)}
                        >
                          <div className="result-meta">
                            <strong>{source?.name ?? '未知来源'}</strong>
                            <span className="result-location">
                              {result.title_path.join(' / ') || '正文'}
                            </span>
                            <span
                              className="result-score"
                              title="词法与向量召回经过排名融合后的相对分数，不代表概率"
                            >
                              相关度 {result.score.toFixed(4)}
                            </span>
                          </div>
                          <p>{expanded ? result.context_text : result.text}</p>
                          <div className="result-footer">
                            <span>
                              {result.page
                                ? `第 ${result.page} 页`
                                : `字符 ${result.matched_range.char_start}–${result.matched_range.char_end}`}
                            </span>
                            {hasMore && (
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  toggleContext(result.context_id)
                                }}
                              >
                                {expanded ? '收起上下文' : '展开上下文'}
                              </button>
                            )}
                          </div>
                        </article>
                      )
                    })}
                  </section>
                )}
                <section className="content-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>资料</h2>
                      <p>
                        {sources.length === 0
                          ? '尚未导入资料'
                          : sourceFilter
                            ? `当前页 ${sources.length} 份匹配资料`
                            : `第 ${sourcePage} 页，共 ${sources.length} 份资料`}
                      </p>
                    </div>
                    <div className="panel-actions">
                      <Button
                        variant="ghost"
                        onClick={() => setShowUrlImport(true)}
                        disabled={busy}
                      >
                        从网页导入
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => fileInput.current?.click()}
                        disabled={busy}
                      >
                        添加本地资料
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => folderInput.current?.click()}
                        disabled={busy}
                      >
                        导入文件夹
                      </Button>
                      <input
                        ref={fileInput}
                        className="visually-hidden"
                        type="file"
                        multiple
                        accept=".md,.markdown,.txt,.pdf,.docx,.pptx,.xlsx,.htm,.html"
                        onChange={(event) => void importFiles(event.target.files)}
                      />
                      <input
                        ref={(node) => {
                          folderInput.current = node
                          node?.setAttribute('webkitdirectory', '')
                        }}
                        className="visually-hidden"
                        type="file"
                        multiple
                        accept=".md,.markdown,.txt,.pdf,.docx,.pptx,.xlsx,.htm,.html"
                        onChange={(event) => prepareFolderImport(event.target.files)}
                      />
                    </div>
                  </div>
                  {sources.length === 0 ? (
                    <button
                      className="drop-zone"
                      type="button"
                      onClick={() => fileInput.current?.click()}
                      disabled={busy}
                    >
                      <span className="drop-icon">⇧</span>
                      <strong>拖放或选择资料</strong>
                      <span>支持 Markdown、TXT、PDF、DOCX、PPTX、XLSX 和 HTML</span>
                    </button>
                  ) : (
                    <>
                      <div className="list-toolbar">
                        <input
                          aria-label="筛选资料"
                          value={sourceFilter}
                          placeholder="按名称、类型或状态筛选"
                          onChange={(event) => {
                            setSourceFilter(event.target.value)
                            setSourceCursor(undefined)
                            setSourceCursorHistory([])
                            setNextSourceCursor(undefined)
                          }}
                        />
                        <select
                          aria-label="资料排序方式"
                          value={sourceSort}
                          onChange={(event) => {
                            setSourceSort(event.target.value as SourceSort)
                            setSourceCursor(undefined)
                            setSourceCursorHistory([])
                            setNextSourceCursor(undefined)
                          }}
                        >
                          <option value="updated-desc">最近更新</option>
                          <option value="name-asc">名称 A–Z</option>
                          <option value="size-desc">文件大小</option>
                        </select>
                      </div>
                      {sources.length === 0 ? (
                        <div className="filter-empty">没有符合当前筛选条件的资料。</div>
                      ) : (
                        <div className="source-table" role="table" aria-label="资料列表">
                          <div className="source-row source-row--header" role="row">
                            <span>名称</span>
                            <span>状态</span>
                            <span>更新时间</span>
                            <span>大小</span>
                          </div>
                          {sources.map((source) => {
                            const job = jobs[source.id]
                            const status =
                              job?.status === 'succeeded' ? 'ready' : (job?.status ?? source.status)
                            return (
                              <button
                                className={`source-row ${source.id === selectedSourceId ? 'source-row--selected' : ''}`}
                                type="button"
                                role="row"
                                key={source.id}
                                onClick={() => openSourceByUser(source.id)}
                              >
                                <span className="source-name">
                                  <span className="file-glyph">▱</span>
                                  <strong>{source.name}</strong>
                                </span>
                                <span className={`status-pill status-pill--${status}`}>
                                  {sourceStatus(status)}
                                  {job && !['succeeded', 'failed'].includes(job.status)
                                    ? ` ${Math.round(job.progress * 100)}%`
                                    : ''}
                                </span>
                                <span>{formatDate(source.updated_at)}</span>
                                <span>{formatBytes(source.size_bytes)}</span>
                                {job?.status === 'failed' && (
                                  <span
                                    className="row-action"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      void retrySource(source.id)
                                    }}
                                  >
                                    重试
                                  </span>
                                )}
                              </button>
                            )
                          })}
                        </div>
                      )}
                      <nav className="pagination" aria-label="资料分页">
                        <button
                          type="button"
                          disabled={sourceCursorHistory.length === 0}
                          onClick={() => {
                            const previous = sourceCursorHistory.at(-1)
                            setSourceCursor(previous || undefined)
                            setSourceCursorHistory((history) => history.slice(0, -1))
                          }}
                        >
                          上一页
                        </button>
                        <span>
                          第 {sourcePage} 页 · 每页 {SOURCE_PAGE_SIZE} 条
                        </span>
                        <button
                          type="button"
                          disabled={!nextSourceCursor}
                          onClick={() => {
                            if (!nextSourceCursor) return
                            setSourceCursorHistory((history) => [...history, sourceCursor ?? ''])
                            setSourceCursor(nextSourceCursor)
                          }}
                        >
                          下一页
                        </button>
                      </nav>
                    </>
                  )}
                </section>
              </section>

              <aside className="detail-pane" aria-label="资料详情">
                {!selectedSource ? (
                  <div className="detail-empty">
                    <span>▱</span>
                    <p>选择资料后可在这里预览原文和引用信息。</p>
                  </div>
                ) : (
                  <>
                    <div className="detail-header">
                      <div className="detail-title">
                        <span className="file-glyph">▱</span>
                        <div>
                          <strong>{selectedSource.name}</strong>
                          <span className={`status-pill status-pill--${selectedSource.status}`}>
                            {sourceStatus(selectedSource.status)}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="detail-actions" aria-label="资料操作">
                      <FavoriteButton key={selectedSource.id} sourceId={selectedSource.id} />
                      <button
                        className="detail-icon-button detail-delete"
                        type="button"
                        aria-label="删除资料"
                        title="删除资料"
                        onClick={() =>
                          setDeleteTarget({
                            kind: 'source',
                            id: selectedSource.id,
                            name: selectedSource.name
                          })
                        }
                        disabled={busy}
                      >
                        <svg aria-hidden="true" viewBox="0 0 24 24">
                          <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
                        </svg>
                      </button>
                    </div>
                    <div className="detail-tabs">
                      <button
                        className={detailTab === 'preview' ? 'active' : ''}
                        type="button"
                        onClick={() => setDetailTab('preview')}
                      >
                        预览
                      </button>
                      <button
                        className={detailTab === 'details' ? 'active' : ''}
                        type="button"
                        onClick={() => setDetailTab('details')}
                      >
                        详情
                      </button>
                    </div>
                    {detailTab === 'preview' ? (
                      <div className="document-preview">
                        {sourceContent ? (
                          <>
                            {!selectedSource.media_type.startsWith('text/') && (
                              <p className="preview-notice">
                                此处显示从原文件安全提取的纯文本，原文件不会被修改。
                              </p>
                            )}
                            <DocumentPreview content={sourceContent} range={highlightRange} />
                          </>
                        ) : (
                          <p>正在读取原文…</p>
                        )}
                      </div>
                    ) : (
                      <dl className="source-details">
                        <div>
                          <dt>文件类型</dt>
                          <dd>{selectedSource.media_type}</dd>
                        </div>
                        <div>
                          <dt>文件大小</dt>
                          <dd>{formatBytes(selectedSource.size_bytes)}</dd>
                        </div>
                        <div>
                          <dt>索引状态</dt>
                          <dd>
                            {sourceStatus(jobs[selectedSource.id]?.status ?? selectedSource.status)}
                          </dd>
                        </div>
                        <div>
                          <dt>添加时间</dt>
                          <dd>{formatDate(selectedSource.created_at)}</dd>
                        </div>
                        <div>
                          <dt>来源 ID</dt>
                          <dd className="mono">{selectedSource.id}</dd>
                        </div>
                        {selectedSource.origin_url && (
                          <div>
                            <dt>网页来源</dt>
                            <dd className="mono source-origin">{selectedSource.origin_url}</dd>
                          </div>
                        )}
                        {highlightRange && (
                          <div>
                            <dt>当前引用</dt>
                            <dd>
                              {highlightRange.page_start
                                ? `第 ${highlightRange.page_start} 页`
                                : `字符 ${highlightRange.char_start}–${highlightRange.char_end}`}
                            </dd>
                          </div>
                        )}
                      </dl>
                    )}
                  </>
                )}
              </aside>
            </div>
          )}
        </section>
      )}

      {settings && !settings.onboarding_completed && (
        <div className="dialog-backdrop onboarding-backdrop" role="presentation">
          <section className="dialog onboarding-dialog" aria-labelledby="onboarding-title">
            <img className="onboarding-mark" src="/loredock-icon.png" alt="" />
            <p className="eyebrow">欢迎来到 LoreDock</p>
            <h2 id="onboarding-title">让资料真正为你所用</h2>
            <p>资料只保存在你的设备上。创建知识库、导入文件后，就能立即搜索并查看精确来源。</p>
            <div className="onboarding-features">
              <span>本地优先</span>
              <span>混合检索</span>
              <span>精确引用</span>
            </div>
            <Button
              onClick={() =>
                void saveSettings({
                  onboarding_completed: true,
                  theme: settings.theme,
                  default_search_mode: settings.default_search_mode
                })
              }
              disabled={busy}
            >
              {busy ? '正在准备…' : '开始使用'}
            </Button>
          </section>
        </div>
      )}

      {showSettings && settings && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={() => setShowSettings(false)}
        >
          <form
            className="dialog settings-dialog"
            aria-labelledby="app-settings-title"
            onSubmit={(event) => {
              event.preventDefault()
              const data = new FormData(event.currentTarget)
              void saveSettings({
                onboarding_completed: true,
                theme: data.get('theme') as AppSettings['theme'],
                default_search_mode: data.get(
                  'default_search_mode'
                ) as AppSettings['default_search_mode']
              })
            }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">应用偏好</p>
            <h2 id="app-settings-title">设置</h2>
            <label htmlFor="theme-preference">外观</label>
            <select id="theme-preference" name="theme" defaultValue={settings.theme}>
              <option value="system">跟随系统</option>
              <option value="light">浅色</option>
              <option value="dark">深色</option>
            </select>
            <label htmlFor="default-search-mode">默认搜索方式</label>
            <select
              id="default-search-mode"
              name="default_search_mode"
              defaultValue={settings.default_search_mode}
            >
              <option value="hybrid">混合检索（推荐）</option>
              <option value="lexical">仅全文检索</option>
            </select>
            <p className="setting-note">混合检索不可用时，LoreDock 仍会保留全文检索能力。</p>
            <section className="model-card" aria-label="本地模型">
              <div>
                <strong>{modelStatus?.display_name ?? '多语言快速模型'}</strong>
                <p>
                  {modelStatus?.active
                    ? '正在使用 · 384 维本地语义检索'
                    : modelStatus?.state === 'ready'
                      ? '安装完成 · 重启 LoreDock 后启用'
                      : modelStatus?.state === 'corrupt'
                        ? '文件校验失败，可以重新安装修复'
                        : '尚未安装 · 当前自动使用全文检索兼容模式'}
                </p>
              </div>
              {!modelStatus?.active &&
                modelStatus?.state !== 'ready' &&
                (!modelJob || modelJob.status === 'succeeded') && (
                  <Button type="button" variant="secondary" onClick={() => void installModel()}>
                    {modelJob?.status === 'failed' || modelJob?.status === 'canceled'
                      ? '继续下载'
                      : modelStatus?.state === 'corrupt'
                        ? '重新安装'
                        : '安装模型'}
                  </Button>
                )}
            </section>
            {modelJob && ['pending', 'running'].includes(modelJob.status) && (
              <section className="model-progress" aria-live="polite">
                <div>
                  <span>
                    {modelJob.current_file ? `正在下载 ${modelJob.current_file}` : '正在准备下载'}
                  </span>
                  <strong>
                    {modelJob.bytes_total
                      ? `${Math.floor((modelJob.bytes_downloaded / modelJob.bytes_total) * 100)}%`
                      : '0%'}
                  </strong>
                </div>
                <progress value={modelJob.bytes_downloaded} max={modelJob.bytes_total || 1} />
                <div>
                  <small>
                    {formatBytes(modelJob.bytes_downloaded)} / {formatBytes(modelJob.bytes_total)}
                  </small>
                  <button type="button" onClick={() => void cancelModel()}>
                    取消
                  </button>
                </div>
              </section>
            )}
            {modelJob && ['failed', 'canceled'].includes(modelJob.status) && (
              <div className="model-job-message">
                <span>
                  {modelJob.status === 'canceled' ? '下载已暂停，可从已有进度继续。' : '下载失败。'}
                </span>
                <button type="button" onClick={() => void retryModel()}>
                  重试
                </button>
              </div>
            )}
            {modelStatus && !modelStatus.active && modelStatus.state !== 'ready' && (
              <p className="setting-note">
                下载约 {formatBytes(modelStatus.download_size_bytes)}，磁盘至少需要{' '}
                {formatBytes(modelStatus.required_space_bytes)} 可用空间。下载地址固定且文件会进行
                SHA-256 校验。
              </p>
            )}
            <div className="dialog-actions">
              <Button type="button" variant="ghost" onClick={() => setShowSettings(false)}>
                取消
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? '正在保存…' : '保存设置'}
              </Button>
            </div>
          </form>
        </div>
      )}

      {showCreate && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={() => setShowCreate(false)}
        >
          <form
            className="dialog"
            aria-labelledby="create-library-title"
            onSubmit={(event) => void createLibrary(event)}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">新建空间</p>
            <h2 id="create-library-title">创建知识库</h2>
            <p>给资料集合取一个容易辨认的名称，之后还可以修改。</p>
            <label htmlFor="library-name">知识库名称</label>
            <input
              id="library-name"
              autoFocus
              maxLength={120}
              value={libraryName}
              onChange={(event) => setLibraryName(event.target.value)}
              placeholder="例如：产品资料"
            />
            <div className="dialog-actions">
              <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>
                取消
              </Button>
              <Button type="submit" disabled={!libraryName.trim() || busy}>
                {busy ? '正在创建…' : '创建'}
              </Button>
            </div>
          </form>
        </div>
      )}

      {showUrlImport && selectedLibrary && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={() => setShowUrlImport(false)}
        >
          <form
            className="dialog"
            aria-labelledby="import-url-title"
            onSubmit={(event) => void importUrl(event)}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">保存网页快照</p>
            <h2 id="import-url-title">从网址导入</h2>
            <p>LoreDock 会保存当前网页的安全文本快照。不会登录网站、执行脚本或持续同步页面。</p>
            <label htmlFor="source-url">网页地址</label>
            <input
              id="source-url"
              type="url"
              inputMode="url"
              autoFocus
              maxLength={2048}
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="https://example.com/article"
            />
            <p className="setting-note">仅支持公开的 HTTP/HTTPS 网页，不支持本机或内网地址。</p>
            <div className="dialog-actions">
              <Button type="button" variant="ghost" onClick={() => setShowUrlImport(false)}>
                取消
              </Button>
              <Button type="submit" disabled={!sourceUrl.trim() || busy}>
                {busy ? '正在导入…' : '导入网页'}
              </Button>
            </div>
          </form>
        </div>
      )}

      {folderPlan && selectedLibrary && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={() => setFolderPlan(undefined)}
        >
          <section
            className="dialog folder-import-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="folder-import-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="folder-import-title">导入“{folderPlan.folderName}”</h2>
            <p>确认后会按文件逐份导入。文件夹本身不会被持续监控，原始文件也不会被修改。</p>
            <div className="folder-import-summary" aria-label="文件夹扫描结果">
              <div>
                <strong>{folderPlan.files.length}</strong>
                <span>可导入</span>
              </div>
              <div>
                <strong>{folderPlan.skipped.length}</strong>
                <span>将跳过</span>
              </div>
              <div>
                <strong>{formatBytes(folderPlan.totalBytes)}</strong>
                <span>导入体积</span>
              </div>
            </div>
            {folderPlan.blockedReason && (
              <p className="folder-import-warning" role="alert">
                {folderPlan.blockedReason}
              </p>
            )}
            {folderPlan.files.length > 0 && (
              <div className="folder-import-files">
                <div className="folder-import-list-heading">
                  <strong>待导入资料</strong>
                  <span>按路径顺序</span>
                </div>
                <ul>
                  {folderPlan.files.slice(0, 8).map((item) => (
                    <li key={item.relativePath}>
                      <span title={item.relativePath}>{item.relativePath}</span>
                      <small>{formatBytes(item.file.size)}</small>
                    </li>
                  ))}
                </ul>
                {folderPlan.files.length > 8 && <p>另有 {folderPlan.files.length - 8} 份资料</p>}
              </div>
            )}
            {folderPlan.skipped.length > 0 && (
              <details className="folder-import-skipped">
                <summary>查看跳过的 {folderPlan.skipped.length} 个文件</summary>
                <ul>
                  {folderPlan.skipped.slice(0, 20).map((item) => (
                    <li key={item.relativePath}>
                      <span title={item.relativePath}>{item.relativePath}</span>
                      <small>{item.reason === 'too-large' ? '超过 100 MiB' : '格式不支持'}</small>
                    </li>
                  ))}
                </ul>
                {folderPlan.skipped.length > 20 && (
                  <p>另有 {folderPlan.skipped.length - 20} 个文件</p>
                )}
              </details>
            )}
            <div className="dialog-actions">
              <Button type="button" variant="ghost" onClick={() => setFolderPlan(undefined)}>
                取消
              </Button>
              <Button
                type="button"
                onClick={() => void importFolder()}
                disabled={Boolean(folderPlan.blockedReason) || folderPlan.files.length === 0}
              >
                导入 {folderPlan.files.length} 份资料
              </Button>
            </div>
          </section>
        </div>
      )}

      {showRename && selectedLibrary && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={() => setShowRename(false)}
        >
          <form
            className="dialog"
            aria-labelledby="rename-library-title"
            onSubmit={(event) => void renameLibrary(event)}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">知识库设置</p>
            <h2 id="rename-library-title">重命名知识库</h2>
            <p>资料和索引不会因为修改显示名称而重建。</p>
            <label htmlFor="rename-library-name">知识库名称</label>
            <input
              id="rename-library-name"
              autoFocus
              maxLength={120}
              value={renameName}
              onChange={(event) => setRenameName(event.target.value)}
            />
            <div className="dialog-actions">
              <Button type="button" variant="ghost" onClick={() => setShowRename(false)}>
                取消
              </Button>
              <Button type="submit" disabled={!renameName.trim() || busy}>
                {busy ? '正在保存…' : '保存'}
              </Button>
            </div>
          </form>
        </div>
      )}

      {deleteTarget && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={() => setDeleteTarget(undefined)}
        >
          <section
            className="dialog confirm-dialog"
            role="alertdialog"
            aria-labelledby="confirm-delete-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="warning-symbol">!</div>
            <h2 id="confirm-delete-title">
              确认删除{deleteTarget.kind === 'library' ? '知识库' : '资料'}？
            </h2>
            <p>
              将删除“{deleteTarget.name}”
              {deleteTarget.kind === 'library'
                ? '及其全部资料、解析产物和索引。'
                : '的可信副本、解析产物和全部索引记录。'}
              此操作无法撤销。
            </p>
            <div className="dialog-actions">
              <Button type="button" variant="ghost" onClick={() => setDeleteTarget(undefined)}>
                取消
              </Button>
              <Button
                type="button"
                className="danger-button"
                onClick={() => void confirmDelete()}
                disabled={busy}
              >
                {busy ? '正在删除…' : '确认删除'}
              </Button>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
