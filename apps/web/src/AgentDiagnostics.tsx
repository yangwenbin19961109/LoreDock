import { useEffect, useId, useRef, useState } from 'react'
import type { Library } from '@loredock/contracts'
import { Button } from '@loredock/ui'
import type { AgentConnection } from './agentApi'
import { CoreApiError } from './api'
import { diagnoseAgent, diagnosticStages, type DiagnosticResult } from './diagnosticApi'

const labels = {
  credential: '系统凭据与授权',
  setup: '启动配置生成',
  libraries: '授权知识库列表',
  search: '本地全文搜索',
  read: '命中引用读取'
}
const remedies: Record<string, string> = {
  credential_missing: '凭据缺失或不匹配，请重新创建连接。',
  credential_store_unavailable: '系统凭据库不可用，请解锁后重试。',
  connection_not_found: '连接已撤销或不存在，请刷新连接列表。',
  bridge_not_packaged: '当前安装包缺少连接程序，请更新或重新安装 LoreDock。',
  access_denied: '此连接无权访问所选知识库，请检查授权后重试。',
  library_not_found: '知识库已不可用，请刷新列表后选择其他知识库。',
  source_not_ready: '资料尚未处理完成，请等待导入完成后重试。',
  source_not_found: '命中资料已不可用，请重新检查。',
  invalid_query: '查询无效，请换用资料中的关键词重试。'
}

export function AgentDiagnostics({
  connection,
  libraries,
  disabled
}: {
  readonly connection: AgentConnection
  readonly libraries: readonly Library[]
  readonly disabled: boolean
}) {
  const id = useId()
  const [query, setQuery] = useState('')
  const [libraryId, setLibraryId] = useState('')
  const [result, setResult] = useState<DiagnosticResult | null>(null)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const pending = useRef<AbortController | null>(null)
  useEffect(
    () => () => {
      pending.current?.abort()
      pending.current = null
    },
    []
  )
  const allowed = libraries.filter((library) => connection.library_ids.includes(library.id))
  const selected = allowed.some((library) => library.id === libraryId) ? libraryId : allowed[0]?.id

  async function run() {
    if (pending.current || disabled) return
    const controller = new AbortController()
    pending.current = controller
    setRunning(true)
    setResult(null)
    setError('')
    const timer = window.setTimeout(() => controller.abort(), 30000)
    try {
      const data = await diagnoseAgent(
        connection.id,
        query.trim() ? { library_id: selected, query: query.trim() } : {},
        controller.signal
      )
      if (pending.current === controller) setResult(data)
    } catch (cause) {
      if (pending.current === controller)
        setError(
          cause instanceof CoreApiError && cause.status === 404
            ? '当前 Core 不支持自检，请更新 LoreDock 后重试。'
            : '未能完成检查。请确认 LoreDock 在线、版本一致后重试；超时不代表连接已失效。'
        )
    } finally {
      window.clearTimeout(timer)
      if (pending.current === controller) {
        pending.current = null
        setRunning(false)
      }
    }
  }

  return (
    <details className="agent-manual agent-diagnostics">
      <summary>检查连接</summary>
      <p>只检查 LoreDock 本地能力，不验证 Agent 接入或连接程序握手。不调用模型。</p>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void run()
        }}
      >
        <label htmlFor={`${id}-library`}>测试知识库</label>
        <select
          id={`${id}-library`}
          value={selected ?? ''}
          disabled={running || disabled || !allowed.length}
          onChange={(event) => {
            setLibraryId(event.target.value)
            setResult(null)
            setError('')
          }}
        >
          {!allowed.length && <option value="">没有可测试的知识库</option>}
          {allowed.map((library) => (
            <option key={library.id} value={library.id}>
              {library.name}
            </option>
          ))}
        </select>
        <label htmlFor={`${id}-query`}>测试关键词（可选）</label>
        <input
          id={`${id}-query`}
          value={query}
          maxLength={2000}
          disabled={running || disabled || !allowed.length}
          onChange={(event) => {
            setQuery(event.target.value)
            setResult(null)
            setError('')
          }}
        />
        <p className="agent-help">
          留空只检查凭据、配置生成和库列表；填写后增加全文搜索与引用读取。关键词不保存在页面之外。
        </p>
        <Button type="submit" disabled={running || disabled || (!!query.trim() && !selected)}>
          {running ? '正在检查…' : '运行本地自检'}
        </Button>
      </form>
      {running && <p role="status">正在检查，最多等待 30 秒…</p>}
      {error && <p role="alert">{error}</p>}
      {result && (
        <div role="status">
          <p>
            {result.status === 'passed'
              ? '本次本地自检通过。'
              : result.status === 'no_matches'
                ? '搜索已完成，但没有命中；请换用资料中的关键词。'
                : (remedies[result.code] ?? '本地检查失败，请确认资料状态后重试。')}
          </p>
          <ul>
            {diagnosticStages.map((stage) => (
              <li key={stage}>
                {labels[stage]}：
                {stage === 'search' && result.status === 'no_matches'
                  ? '无命中'
                  : result.completed.includes(stage)
                    ? '通过'
                    : result.stage === stage && result.status === 'failed'
                      ? '失败'
                      : '未检查'}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="agent-help">
        Agent 接入尚未由此检查验证。请在 Agent
        中发起一次新的搜索并读取引用；结果仅代表本次检查，不是实时连接状态。
      </p>
    </details>
  )
}
