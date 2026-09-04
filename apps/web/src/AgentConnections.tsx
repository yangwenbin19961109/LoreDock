import { useEffect, useState } from 'react'
import type { Library } from '@loredock/contracts'
import { Button } from '@loredock/ui'
import { agentApi, type AgentConnection, type AgentSetup } from './agentApi'
import { ManualAgentSetup } from './ManualAgentSetup'
import { AgentDiagnostics } from './AgentDiagnostics'

export function AgentConnections({ libraries }: { readonly libraries: readonly Library[] }) {
  const [connections, setConnections] = useState<AgentConnection[]>([])
  const [name, setName] = useState('我的 Agent')
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [setup, setSetup] = useState<AgentSetup | null>(null)
  const instructions = setup?.instructions ?? ''
  const [activeId, setActiveId] = useState('')
  const [confirmId, setConfirmId] = useState('')

  async function refresh() {
    setLoading(true)
    setError('')
    try {
      const items = await agentApi.list()
      setConnections(items)
      if (activeId && !items.some((item) => item.id === activeId)) {
        setSetup(null)
        setActiveId('')
      }
    } catch {
      setError('无法读取连接。请在桌面应用中确认 Core 已连接后重试。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    void agentApi
      .list()
      .then((items) => {
        if (active) setConnections(items)
      })
      .catch(() => {
        if (active) setError('无法读取连接。请在桌面应用中确认 Core 已连接后重试。')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  async function showInstructions(id: string) {
    setBusy(true)
    setError('')
    setNotice('')
    setSetup(null)
    setActiveId(id)
    try {
      setSetup(await agentApi.setup(id))
    } catch {
      setError('未能生成说明。请刷新列表重试；当前安装包可能尚未包含独立 bridge。')
    } finally {
      setBusy(false)
    }
  }

  async function create() {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const allowed = selected.filter((id) => libraries.some((library) => library.id === id))
      const connection = await agentApi.create(name.trim(), allowed)
      setConnections((current) => [connection, ...current])
      setSelected([])
      await showInstructions(connection.id)
    } catch {
      setError(
        '无法创建连接。请确认 Core 在线、系统凭据库已解锁，并检查连接数量是否达到 100 个上限。'
      )
    } finally {
      setBusy(false)
    }
  }

  async function revoke(connection: AgentConnection) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const cleaned = await agentApi.revoke(connection.id)
      setConnections((current) => current.filter((item) => item.id !== connection.id))
      if (activeId === connection.id) {
        setSetup(null)
        setActiveId('')
      }
      setConfirmId('')
      setNotice(
        cleaned
          ? '连接已撤销，Agent 不再能通过它访问知识库。'
          : '访问已撤销，但系统凭据未清理成功，请稍后检查系统凭据库。'
      )
    } catch {
      setError('撤销结果未确认，请刷新列表后重试。')
    } finally {
      setBusy(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(instructions)
      setNotice('已复制。请粘贴给同一台电脑上的 Agent，让它添加 MCP 并验证。')
    } catch {
      setNotice('无法访问剪贴板，请选中下方说明并手动复制。')
    }
  }

  return (
    <section className="agent-area" aria-labelledby="agent-heading">
      <header className="agent-heading">
        <h1 id="agent-heading">Agent 连接</h1>
        <p>选好知识库，复制一段说明，让 Agent 帮你完成连接。</p>
      </header>
      {error && (
        <p role="alert" className="agent-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="agent-notice">
          {notice}
        </p>
      )}
      <div className="agent-columns">
        <div>
          <form
            className="agent-form"
            onSubmit={(event) => {
              event.preventDefault()
              void create()
            }}
          >
            <h2>创建只读连接</h2>
            <label htmlFor="agent-name">连接名称</label>
            <input
              id="agent-name"
              value={name}
              maxLength={120}
              required
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
            <fieldset disabled={busy}>
              <legend>允许访问的知识库</legend>
              <div className="agent-library-list">
                {libraries.map((library) => (
                  <label key={library.id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(library.id)}
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, library.id]
                            : current.filter((id) => id !== library.id)
                        )
                      }
                    />
                    <span>{library.name}</span>
                  </label>
                ))}
              </div>
              {libraries.length === 0 && <p>请先返回“全部知识库”创建知识库。</p>}
            </fieldset>
            <p className="agent-help">只能搜索和读取你选中的资料，不能删除或修改。可随时撤销。</p>
            <Button type="submit" disabled={busy || loading || !selected.length || !name.trim()}>
              {busy ? '正在处理…' : '生成连接说明'}
            </Button>
          </form>
          <section className="agent-existing" aria-label="已有连接">
            <div className="agent-row">
              <h2>已有连接</h2>
              <Button variant="ghost" disabled={busy || loading} onClick={() => void refresh()}>
                刷新
              </Button>
            </div>
            {loading ? (
              <p role="status">正在读取连接…</p>
            ) : connections.length === 0 ? (
              <p>还没有连接。创建后可在这里重新获取说明或撤销授权。</p>
            ) : (
              <ul>
                {connections.map((connection) => (
                  <li key={connection.id}>
                    <strong>{connection.name}</strong>
                    <p>
                      {connection.library_ids
                        .map(
                          (id) =>
                            libraries.find((library) => library.id === id)?.name ?? '已删除的知识库'
                        )
                        .join('、')}
                    </p>
                    <div className="agent-row">
                      <Button
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void showInstructions(connection.id)}
                      >
                        查看说明
                      </Button>
                      {confirmId !== connection.id ? (
                        <Button
                          variant="ghost"
                          disabled={busy}
                          onClick={() => setConfirmId(connection.id)}
                        >
                          撤销连接
                        </Button>
                      ) : (
                        <>
                          <Button disabled={busy} onClick={() => void revoke(connection)}>
                            确认撤销
                          </Button>
                          <Button variant="ghost" disabled={busy} onClick={() => setConfirmId('')}>
                            取消
                          </Button>
                        </>
                      )}
                    </div>
                    <AgentDiagnostics
                      key={JSON.stringify([
                        connection.library_ids,
                        libraries.map((library) => library.id)
                      ])}
                      connection={connection}
                      libraries={libraries}
                      disabled={busy || loading}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <section className="agent-copy" aria-labelledby="agent-copy-heading">
          <h2 id="agent-copy-heading">复制给 Agent</h2>
          <p>说明中不包含令牌。Agent 需要具备编辑 MCP 配置的能力，必要时仍会向你申请权限。</p>
          {instructions ? (
            <>
              <Button onClick={() => void copy()}>复制连接说明</Button>
              <label htmlFor="agent-instructions">连接说明（可手动选择复制）</label>
              <textarea id="agent-instructions" readOnly value={instructions} spellCheck={false} />
              <ManualAgentSetup key={activeId} configurations={setup?.configurations} />
            </>
          ) : (
            <p className="agent-copy-empty">创建连接或选择“查看说明”后，安装说明会显示在这里。</p>
          )}
          <p className="agent-help">
            请保持 LoreDock 打开，并在同一台电脑、同一系统用户下使用。复制说明后，请让 Agent
            发起一次新的检索验证。Core 在线、配置已复制，都不代表 Agent 已成功接入。
          </p>
        </section>
      </div>
    </section>
  )
}
