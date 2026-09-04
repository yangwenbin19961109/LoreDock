import { afterEach, expect, it, vi } from 'vitest'
import { agentApi, parseConnection, parseSetup } from './agentApi'

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
  expect(await agentApi.setup('a/b')).toEqual({ instructions: 'MCP setup' })
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/agent-connections/a%2Fb/setup', undefined)
})

it('accepts bounded manual configurations and ignores unknown fields', () => {
  expect(
    parseSetup({
      instructions: 'setup',
      configurations: { codex: 'toml', cursor: 'json', extra: 'ignored' }
    })
  ).toEqual({ instructions: 'setup', configurations: { codex: 'toml', cursor: 'json' } })
})

it.each([
  null,
  [],
  {},
  { codex: 1, cursor: 'json' },
  { codex: '', cursor: 'json' },
  { codex: 'x'.repeat(50001), cursor: 'json' }
])('rejects malformed manual configurations: %j', (configurations) => {
  expect(() => parseSetup({ instructions: 'setup', configurations })).toThrow()
})
