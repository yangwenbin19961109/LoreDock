import { afterEach, expect, it, vi } from 'vitest'
import { agentApi, parseConnection } from './agentApi'

afterEach(() => vi.unstubAllGlobals())

it('rejects malformed connection scopes', () => {
  expect(() =>
    parseConnection({ id: 'a', name: 'A', created_at: 'today', library_ids: [3] })
  ).toThrow()
})

it('retrieves non-secret setup text from the owner endpoint', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ instructions: 'MCP setup', runtime: 'development' }))
    )
  vi.stubGlobal('fetch', fetchMock)
  expect(await agentApi.setup('a/b')).toBe('MCP setup')
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/agent-connections/a%2Fb/setup', undefined)
})
