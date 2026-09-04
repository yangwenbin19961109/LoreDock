import { request } from './api'

export const diagnosticStages = ['credential', 'setup', 'libraries', 'search', 'read'] as const
export type DiagnosticStage = (typeof diagnosticStages)[number]
export interface DiagnosticResult {
  readonly status: 'passed' | 'no_matches' | 'failed'
  readonly stage: DiagnosticStage
  readonly code: string
  readonly completed: readonly DiagnosticStage[]
}

function isStage(value: unknown): value is DiagnosticStage {
  return diagnosticStages.some((stage) => stage === value)
}

export function parseDiagnostic(value: unknown): DiagnosticResult {
  if (!value || typeof value !== 'object') throw new Error('Invalid diagnostic')
  const data = value as Record<string, unknown>
  if (
    data.scope !== 'local_core' ||
    data.external_agent_verified !== false ||
    !['passed', 'no_matches', 'failed'].includes(String(data.status)) ||
    !isStage(data.stage) ||
    typeof data.code !== 'string' ||
    data.code.length > 128 ||
    !Array.isArray(data.completed) ||
    !data.completed.every(isStage) ||
    data.completed.some((stage, index) => diagnosticStages[index] !== stage)
  )
    throw new Error('Invalid diagnostic')
  const count = diagnosticStages.indexOf(data.stage)
  if (
    data.completed.length !== count + (data.status === 'failed' ? 0 : 1) ||
    (data.status === 'passed' && data.stage !== 'libraries' && data.stage !== 'read') ||
    (data.status === 'no_matches' && data.stage !== 'search')
  )
    throw new Error('Invalid diagnostic')
  return {
    status: data.status as DiagnosticResult['status'],
    stage: data.stage,
    code: data.code,
    completed: data.completed
  }
}

export async function diagnoseAgent(
  id: string,
  payload: { library_id?: string; query?: string },
  signal: AbortSignal
): Promise<DiagnosticResult> {
  return parseDiagnostic(
    await request<unknown>(`agent-connections/${encodeURIComponent(id)}/diagnostics`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal
    })
  )
}
