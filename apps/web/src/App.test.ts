import { describe, expect, it } from 'vitest'

import { coreEndpoint } from '@loredock/contracts'

describe('LoreDock web boundary', () => {
  it('uses the shared versioned Core contract', () => {
    expect(coreEndpoint('health')).toBe('/api/v1/health')
  })
})
