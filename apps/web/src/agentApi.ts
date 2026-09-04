import { request } from './api'

export interface AgentConnection {
  readonly id: string
  readonly name: string
  readonly library_ids: readonly string[]
  readonly created_at: string
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('连接数据格式不兼容，请更新 LoreDock。')
  return value as Record<string, unknown>
}

export function parseConnection(value: unknown): AgentConnection {
  const data = object(value)
  if (
    typeof data.id !== 'string' ||
    typeof data.name !== 'string' ||
    typeof data.created_at !== 'string' ||
    !Array.isArray(data.library_ids) ||
    !data.library_ids.every((id: unknown) => typeof id === 'string')
  ) {
    throw new Error('连接数据格式不兼容，请更新 LoreDock。')
  }
  return {
    id: data.id,
    name: data.name,
    created_at: data.created_at,
    library_ids: data.library_ids
  }
}

export const agentApi = {
  async list(): Promise<AgentConnection[]> {
    const data = object(await request<unknown>('agent-connections'))
    if (!Array.isArray(data.items)) throw new Error('无法读取连接列表，请重试。')
    return data.items.map(parseConnection)
  },
  async create(name: string, library_ids: readonly string[]): Promise<AgentConnection> {
    return parseConnection(
      await request<unknown>('agent-connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, library_ids })
      })
    )
  },
  async setup(id: string): Promise<string> {
    const data = object(await request<unknown>(`agent-connections/${encodeURIComponent(id)}/setup`))
    if (typeof data.instructions !== 'string' || data.instructions.length > 50000)
      throw new Error('连接说明格式不兼容。')
    return data.instructions
  },
  async revoke(id: string): Promise<boolean> {
    const data = object(
      await request<unknown>(`agent-connections/${encodeURIComponent(id)}`, { method: 'DELETE' })
    )
    if (data.revoked !== true || typeof data.credential_removed !== 'boolean')
      throw new Error('未能确认撤销结果，请刷新连接列表。')
    return data.credential_removed
  }
}
