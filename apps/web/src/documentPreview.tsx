import { createElement, type ReactNode, useEffect, useRef } from 'react'

import type { CitationRange, SourceContentResponse } from '@loredock/contracts'
import { buildPreviewBlocks } from './previewBlocks'

function highlightedText(text: string, absoluteStart: number, range?: CitationRange): ReactNode {
  if (!range) return text
  const start = Math.max(0, range.char_start - absoluteStart)
  const end = Math.min(text.length, range.char_end - absoluteStart)
  if (start >= end) return text
  return (
    <>
      {text.slice(0, start)}
      <mark data-preview-highlight="true">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  )
}

export function DocumentPreview({
  content,
  range
}: {
  readonly content: SourceContentResponse
  readonly range?: CitationRange
}) {
  const previewRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!range) return
    previewRef.current
      ?.querySelector('[data-preview-highlight="true"]')
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [content.source_id, range])

  return (
    <article className="preview-document" ref={previewRef}>
      {buildPreviewBlocks(content.text).map((block, index) => {
        const body = highlightedText(block.text, content.char_start + block.start, range)
        const key = `${block.start}-${block.kind}-${index}`
        if (block.kind === 'heading') {
          const heading = `h${Math.min(block.level ?? 2, 6)}` as 'h1'
          return createElement(heading, { key }, body)
        }
        if (block.kind === 'list-item')
          return (
            <div className="preview-list-item" key={key}>
              <span aria-hidden="true">•</span>
              <span>{body}</span>
            </div>
          )
        if (block.kind === 'code')
          return (
            <pre key={key}>
              <code>{body}</code>
            </pre>
          )
        if (block.kind === 'page-break')
          return (
            <div className="preview-page-break" key={key}>
              分页
            </div>
          )
        return <p key={key}>{body}</p>
      })}
    </article>
  )
}
