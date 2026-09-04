import { afterEach, expect, it, vi } from 'vitest'
import { diagnoseAgent, parseDiagnostic } from './diagnosticApi'

const valid = {
  scope: 'local_core',
  external_agent_verified: false,
  status: 'passed',
  stage: 'libraries',
  code: 'local_check_passed',
  completed: ['credential', 'setup', 'libraries']
}
afterEach(() => vi.unstubAllGlobals())
it('accepts the local-only baseline', () => {
  expect(parseDiagnostic(valid).status).toBe('passed')
})
it.each([
  { external_agent_verified: true },
  { scope: 'agent' },
  { stage: 'unknown' },
  { completed: ['credential', 'read'] },
  { status: 'passed', stage: 'search' },
  { status: 'no_matches' },
  { completed: [] },
  { code: 5 }
])('rejects inconsistent or incompatible diagnostics %j', (change) => {
  expect(() => parseDiagnostic({ ...valid, ...change })).toThrow()
})
it('posts a bounded query to an encoded connection path with cancellation', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(valid)))
  vi.stubGlobal('fetch', fetchMock)
  const controller = new AbortController()
  await diagnoseAgent('a/b', { library_id: 'fixture', query: 'sample' }, controller.signal)
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/v1/agent-connections/a%2Fb/diagnostics',
    expect.objectContaining({
      method: 'POST',
      signal: controller.signal,
      body: JSON.stringify({ library_id: 'fixture', query: 'sample' })
    })
  )
})
