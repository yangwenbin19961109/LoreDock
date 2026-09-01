import { coreEndpoint, type HealthResponse } from '@loredock/contracts'
import { Button } from '@loredock/ui'
import { useEffect, useState } from 'react'

type CoreState = 'checking' | 'ready' | 'offline'

async function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(coreEndpoint('health'), { signal })
  if (!response.ok) {
    throw new Error(`Core health check failed with ${response.status}`)
  }
  return (await response.json()) as HealthResponse
}

export function App() {
  const [coreState, setCoreState] = useState<CoreState>('checking')
  const [coreVersion, setCoreVersion] = useState<string>()

  useEffect(() => {
    const controller = new AbortController()
    void fetchHealth(controller.signal)
      .then((health) => {
        setCoreVersion(health.version)
        setCoreState('ready')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setCoreState('offline')
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="welcome-shell">
      <section className="welcome-card" aria-labelledby="welcome-title">
        <img className="brand-mark" src="/loredock-icon.png" alt="" />
        <p className="eyebrow">LOREDOCK · 知坞</p>
        <h1 id="welcome-title">把知识安放好，再交给 Agent 使用。</h1>
        <p className="welcome-copy">
          Phase 0 工程骨架已经就绪。接下来将验证文档解析、混合检索和精确引用。
        </p>
        <div className={`core-status core-status--${coreState}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          {coreState === 'checking' && '正在连接 LoreDock Core'}
          {coreState === 'ready' && `LoreDock Core ${coreVersion ?? ''} 已连接`}
          {coreState === 'offline' && 'LoreDock Core 尚未启动'}
        </div>
        <div className="welcome-actions">
          <Button disabled>创建知识库</Button>
          <Button variant="secondary" disabled>
            导入资料
          </Button>
        </div>
        <p className="phase-note">功能将在后续阶段启用；当前页面仅验证应用边界与设计系统。</p>
      </section>
    </main>
  )
}
