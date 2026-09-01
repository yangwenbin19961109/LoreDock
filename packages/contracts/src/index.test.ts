import { describe, expect, it } from 'vitest'

import { API_VERSION, coreEndpoint } from './index'

describe('Core API contract', () => {
  it('builds versioned endpoints', () => {
    expect(API_VERSION).toBe('v1')
    expect(coreEndpoint('/health')).toBe('/api/v1/health')
    expect(coreEndpoint('libraries/library-id/search')).toBe('/api/v1/libraries/library-id/search')
  })
})
