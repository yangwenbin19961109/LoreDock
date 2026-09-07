import { useEffect, useRef, useState } from 'react'
import type { Library } from '@loredock/contracts'
import { Button } from '@loredock/ui'
import { activityApi, type ActivitySource, type CollectionKind } from './activityApi'
import { FavoriteButton } from './FavoriteButton'

export function SourceCollection({
  kind,
  libraries
}: {
  readonly kind: CollectionKind
  readonly libraries: readonly Library[]
}) {
  const [items, setItems] = useState<ActivitySource[]>([])
  const [next, setNext] = useState<string>()
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<ActivitySource>()
  const [text, setText] = useState<string>()
  const [previewError, setPreviewError] = useState('')
  const listRequest = useRef<AbortController | null>(null)
  const readRequest = useRef<AbortController | null>(null)
  async function load(offset = '0') {
    listRequest.current?.abort()
    const controller = new AbortController()
    listRequest.current = controller
    setBusy(true)
    setError('')
    try {
      const page = await activityApi.list(kind, offset, controller.signal)
      if (controller.signal.aborted) return
      setItems((current) =>
        offset === '0'
          ? page.items
          : [...current, ...page.items.filter((item) => !current.some((old) => old.id === item.id))]
      )
      setNext(page.next)
      if (offset === '0') {
        readRequest.current?.abort()
        setSelected(undefined)
        setText(undefined)
      }
    } catch {
      if (!controller.signal.aborted) setError('列表加载失败，请确认 Core 已更新并在线后刷新。')
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  useEffect(() => {
    const controller = new AbortController()
    listRequest.current = controller
    void activityApi
      .list(kind, '0', controller.signal)
      .then((page) => {
        if (!controller.signal.aborted) {
          setItems(page.items)
          setNext(page.next)
          setBusy(false)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError('列表加载失败，请确认 Core 已更新并在线后刷新。')
          setBusy(false)
        }
      })
    return () => {
      listRequest.current?.abort()
      readRequest.current?.abort()
    }
  }, [kind])
  async function open(item: ActivitySource) {
    readRequest.current?.abort()
    const controller = new AbortController()
    readRequest.current = controller
    setSelected(item)
    setText(undefined)
    setPreviewError('')
    try {
      const content = await activityApi.preview(item.id, controller.signal)
      if (controller.signal.aborted) return
      setText(content)
      try {
        await activityApi.visit(item.id)
      } catch {
        if (!controller.signal.aborted)
          setPreviewError('资料已打开，但最近使用记录未保存。请重新打开重试。')
      }
    } catch {
      if (!controller.signal.aborted)
        setPreviewError('资料无法打开，可能已删除或尚未处理完成。请刷新列表后重试。')
    }
  }
  return (
    <section
      className="collection-area"
      aria-label={kind === 'recent' ? '最近使用资料' : '收藏资料列表'}
    >
      <header className="agent-row">
        <h1>{kind === 'recent' ? '最近使用' : '收藏'}</h1>
        <Button disabled={busy} onClick={() => void load()}>
          刷新列表
        </Button>
      </header>
      <p className="agent-help">
        {kind === 'recent'
          ? '最近打开的 100 份资料，按访问时间排列。后台读取和 Agent 搜索不会记录。'
          : '收藏常用资料，方便下次找到。按收藏时间排列。'}
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="collection-columns">
        <section className="collection-list-pane" aria-label="资料列表">
          {busy && <p role="status">正在读取列表…</p>}
          {!busy && !error && !items.length && (
            <p>
              {kind === 'recent'
                ? '还没有访问记录。请在知识库中点击一份资料。'
                : '还没有收藏。请在资料预览中点击“收藏资料”。'}
            </p>
          )}
          <ul>
            {items.map((item) => (
              <li key={item.id}>
                <button
                  className="collection-source"
                  aria-pressed={selected?.id === item.id}
                  onClick={() => void open(item)}
                >
                  <strong>{item.name}</strong>
                  <span>
                    {libraries.find((library) => library.id === item.library_id)?.name ?? '知识库'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {next && (
            <Button disabled={busy} onClick={() => void load(next)}>
              加载更多
            </Button>
          )}
        </section>
        <section className="collection-preview-pane" aria-label="资料预览">
          {selected ? (
            <>
              <h2>{selected.name}</h2>
              <FavoriteButton
                key={selected.id}
                sourceId={selected.id}
                onChange={() => {
                  if (kind === 'favorites') void load()
                }}
              />
              {previewError && <p role="alert">{previewError}</p>}
              {text === undefined && !previewError ? (
                <p role="status">正在打开资料…</p>
              ) : (
                <pre className="collection-preview">{text}</pre>
              )}
              <p className="agent-help">
                显示解析文本的前 8000 字符，完整资料可在所属知识库中查看。
              </p>
            </>
          ) : (
            <p>选择资料即可预览。</p>
          )}
        </section>
      </div>
    </section>
  )
}
