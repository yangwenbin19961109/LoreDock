import { expect, it } from 'vitest'
import { parseCollection, parseFavorite } from './activityApi'

it('validates favorite booleans', () => {
  expect(parseFavorite({ favorite: true })).toBe(true)
  expect(() => parseFavorite({ favorite: 'true' })).toThrow()
})
it('validates collection pagination and projects only needed fields', () => {
  expect(
    parseCollection({
      items: [{ id: 'a', library_id: 'b', name: '测试', ignored: true }],
      page: { next_cursor: '50' }
    })
  ).toEqual({ items: [{ id: 'a', library_id: 'b', name: '测试' }], next: '50' })
})
it.each([
  null,
  { items: [null], page: {} },
  { items: [], page: { next_cursor: '../x' } },
  { items: [], page: { next_cursor: '9999999999999999999999' } }
])('rejects incompatible collection data %j', (value) => {
  expect(() => parseCollection(value)).toThrow()
})
