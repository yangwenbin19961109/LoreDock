export type PreviewBlockKind = 'heading' | 'paragraph' | 'list-item' | 'code' | 'page-break'

export interface PreviewBlock {
  readonly kind: PreviewBlockKind
  readonly text: string
  readonly start: number
  readonly end: number
  readonly level?: number
}

interface MutableBlock {
  kind: PreviewBlockKind
  text: string
  start: number
  end: number
  level?: number
}

export function buildPreviewBlocks(text: string): readonly PreviewBlock[] {
  const blocks: MutableBlock[] = []
  let offset = 0
  let paragraph: MutableBlock | undefined
  let code: MutableBlock | undefined

  function flushParagraph(): void {
    if (paragraph) blocks.push(paragraph)
    paragraph = undefined
  }

  for (const lineWithEnding of text.match(/.*(?:\n|$)/g) ?? []) {
    if (!lineWithEnding) continue
    const line = lineWithEnding.endsWith('\n') ? lineWithEnding.slice(0, -1) : lineWithEnding
    const lineEnd = offset + line.length
    if (/^\s*```/.test(line)) {
      flushParagraph()
      if (code) {
        blocks.push(code)
        code = undefined
      } else {
        code = { kind: 'code', text: '', start: lineEnd + 1, end: lineEnd + 1 }
      }
      offset += lineWithEnding.length
      continue
    }
    if (code) {
      code.text += `${code.text ? '\n' : ''}${line}`
      code.end = lineEnd
      offset += lineWithEnding.length
      continue
    }
    if (line.includes('\f')) {
      flushParagraph()
      blocks.push({ kind: 'page-break', text: '', start: offset, end: lineEnd })
      offset += lineWithEnding.length
      continue
    }
    if (!line.trim()) {
      flushParagraph()
      offset += lineWithEnding.length
      continue
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      const marks = heading[1]
      const content = heading[2]
      if (!marks || !content) continue
      flushParagraph()
      const contentStart = offset + marks.length + 1
      blocks.push({
        kind: 'heading',
        text: content,
        start: contentStart,
        end: lineEnd,
        level: marks.length
      })
      offset += lineWithEnding.length
      continue
    }
    const listItem = line.match(/^\s*(?:[-*+]|\d+\.)\s+(.+)$/)
    if (listItem) {
      const content = listItem[1]
      if (!content) continue
      flushParagraph()
      const contentStart = offset + line.indexOf(content)
      blocks.push({ kind: 'list-item', text: content, start: contentStart, end: lineEnd })
      offset += lineWithEnding.length
      continue
    }
    if (!paragraph) {
      paragraph = { kind: 'paragraph', text: line, start: offset, end: lineEnd }
    } else {
      paragraph.text += `\n${line}`
      paragraph.end = lineEnd
    }
    offset += lineWithEnding.length
  }
  flushParagraph()
  if (code) blocks.push(code)
  return blocks
}
