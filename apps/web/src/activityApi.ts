import { request } from './api'

export type CollectionKind = 'recent' | 'favorites'
export interface ActivitySource {
  readonly id: string
  readonly library_id: string
  readonly name: string
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Invalid activity response')
  return value as Record<string, unknown>
}
export function parseFavorite(value: unknown): boolean {
  const data = object(value)
  if (typeof data.favorite !== 'boolean') throw new Error('Invalid favorite state')
  return data.favorite
}
export function parseCollection(value: unknown): { items: ActivitySource[]; next?: string } {
  const data = object(value),
    page = object(data.page)
  if (!Array.isArray(data.items) || data.items.length > 50) throw new Error('Invalid collection')
  const items = data.items.map((value: unknown) => {
    const item = object(value)
    if (
      typeof item.id !== 'string' ||
      !item.id ||
      typeof item.library_id !== 'string' ||
      typeof item.name !== 'string'
    )
      throw new Error('Invalid source')
    return { id: item.id, library_id: item.library_id, name: item.name }
  })
  const next = page.next_cursor
  if (
    next != null &&
    (typeof next !== 'string' || !/^\d+$/.test(next) || !Number.isSafeInteger(Number(next)))
  )
    throw new Error('Invalid cursor')
  return { items, next: typeof next === 'string' ? next : undefined }
}
export const activityApi = {
  async list(kind: CollectionKind, offset = '0', signal?: AbortSignal) {
    return parseCollection(
      await request<unknown>(
        `source-collections/${kind}?limit=50&offset=${encodeURIComponent(offset)}`,
        { signal }
      )
    )
  },
  async favorite(id: string, signal?: AbortSignal) {
    return parseFavorite(
      await request<unknown>(`sources/${encodeURIComponent(id)}/favorite`, { signal })
    )
  },
  async setFavorite(id: string, favorite: boolean) {
    return parseFavorite(
      await request<unknown>(`sources/${encodeURIComponent(id)}/favorite`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ favorite })
      })
    )
  },
  async visit(id: string) {
    await request<unknown>(`sources/${encodeURIComponent(id)}/visit`, { method: 'POST' })
  },
  async preview(id: string, signal: AbortSignal): Promise<string> {
    const data = object(
      await request<unknown>(`sources/${encodeURIComponent(id)}/content`, { signal })
    )
    if (data.source_id !== id || typeof data.text !== 'string') throw new Error('Invalid preview')
    return data.text
  }
}
