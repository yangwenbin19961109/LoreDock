import { useState } from 'react'
import { Button } from '@loredock/ui'
import type { AgentSetup } from './agentApi'

const clients = {
  codex: {
    label: 'Codex',
    location:
      '用户目录下的 .codex/config.toml（如果设置了 CODEX_HOME，则使用该目录）。也可使用受信任项目中的 .codex/config.toml。',
    merge:
      '将下方独立配置段合并到文件中，保留其他设置。如果已有同名的 LoreDock 配置段，只更新该段，不要重复添加。',
    reload: '保存后，在客户端的 MCP 设置中重新启动此服务，或重启客户端并开启新会话。',
    format: 'TOML'
  },
  cursor: {
    label: 'Cursor',
    location: '用户目录下的 .cursor/mcp.json；仅用于当前项目时，使用项目中的 .cursor/mcp.json。',
    merge:
      '文件不存在时可使用下方完整 JSON；已有文件时，只合并 mcpServers 内的 LoreDock 条目，保留其他服务，注意逗号。不要覆盖整个文件。',
    reload:
      '保存后重新加载或重启 Cursor，在 MCP 设置中确认服务已启用，再开启新会话。Cursor 实机验收暂缓，此处仅提供配置模板。',
    format: 'JSON'
  }
} as const

export function ManualAgentSetup({ configurations }: Pick<AgentSetup, 'configurations'>) {
  const [client, setClient] = useState<keyof typeof clients>('codex')
  const [notice, setNotice] = useState('')
  const guide = clients[client]

  async function copy() {
    if (!configurations) return
    try {
      await navigator.clipboard.writeText(configurations[client])
      setNotice('配置已复制，尚未写入客户端。请按上方步骤合并并验证。')
    } catch {
      setNotice('无法访问剪贴板，请选中下方配置并手动复制。')
    }
  }

  return (
    <details className="agent-manual">
      <summary>Agent 没能自动配置？手动添加</summary>
      <p>也可让 Agent 在你批准后重试。不要关闭安全限制或向它提供系统令牌。</p>
      {!configurations ? (
        <p>当前 Core 未提供手动配置，请更新 LoreDock 后重新查看连接说明。</p>
      ) : (
        <>
          <label htmlFor="agent-client">选择客户端</label>
          <select
            id="agent-client"
            value={client}
            onChange={(event) => {
              const value = event.target.value
              if (value === 'codex' || value === 'cursor') {
                setClient(value)
                setNotice('')
              }
            }}
          >
            <option value="codex">Codex</option>
            <option value="cursor">Cursor</option>
          </select>
          <ol>
            <li>
              先备份配置文件，再打开：{guide.location} 用户目录指你当前系统账户的主文件夹，不是
              LoreDock 安装目录。
            </li>
            <li>{guide.merge}</li>
            <li>{guide.reload}</li>
            <li>
              保持 LoreDock 打开，让 Agent 调用
              list_libraries，再搜索一条测试资料并读取引用。工具列表可见不等于检索成功。
            </li>
          </ol>
          <Button variant="ghost" onClick={() => void copy()}>
            复制 {guide.label} 配置
          </Button>
          {notice && <p role="status">{notice}</p>}
          <label htmlFor="agent-manual-config">
            {guide.label} 配置（{guide.format}，可手动选择复制）
          </label>
          <textarea
            id="agent-manual-config"
            readOnly
            value={configurations[client]}
            spellCheck={false}
          />
          <p className="agent-help">
            仅包含本机启动路径和连接
            ID，不含令牌。不要上传到公共仓库；撤销连接后请从客户端移除对应条目。
          </p>
        </>
      )}
    </details>
  )
}
