import { describe, expect, it } from 'vitest'

import { buildPreviewBlocks } from './previewBlocks'

describe('document preview structure', () => {
  it('recognizes headings, lists, code, and page boundaries without changing offsets', () => {
    const text = '# 标题\n\n正文第一行\n正文第二行\n\n- 项目\n\n```ts\nconst safe = true\n```\n\f\n'
    const blocks = buildPreviewBlocks(text)

    expect(blocks.map((block) => block.kind)).toEqual([
      'heading',
      'paragraph',
      'list-item',
      'code',
      'page-break'
    ])
    const heading = blocks[0]
    const listItem = blocks[2]
    const code = blocks[3]
    expect(heading).toBeDefined()
    expect(listItem).toBeDefined()
    expect(code).toBeDefined()
    if (!heading || !listItem || !code) throw new Error('Expected preview blocks were not built')
    expect(text.slice(heading.start, heading.end)).toBe('标题')
    expect(text.slice(listItem.start, listItem.end)).toBe('项目')
    expect(code.text).toBe('const safe = true')
  })

  it('returns plain text as a safe paragraph instead of HTML', () => {
    const blocks = buildPreviewBlocks('<script>alert(1)</script>')

    expect(blocks).toEqual([
      { kind: 'paragraph', text: '<script>alert(1)</script>', start: 0, end: 25 }
    ])
  })
})
