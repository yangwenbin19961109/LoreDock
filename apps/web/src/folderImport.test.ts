import { describe, expect, it } from 'vitest'

import { MAX_FOLDER_FILE_COUNT, MAX_SOURCE_BYTES, planFolderImport } from './folderImport'

function folderFile(path: string, size = 4): File {
  const file = new File([new Uint8Array(size)], path.split('/').at(-1) ?? path)
  Object.defineProperty(file, 'webkitRelativePath', { value: path })
  return file
}

describe('folder import preflight', () => {
  it('keeps supported files in deterministic relative-path order', () => {
    const plan = planFolderImport([
      folderFile('资料库/二级/B.PDF'),
      folderFile('资料库/a.md'),
      folderFile('资料库/图片.png')
    ])

    expect(plan.folderName).toBe('资料库')
    expect(plan.files.map((item) => item.relativePath)).toEqual([
      '资料库/二级/B.PDF',
      '资料库/a.md'
    ])
    expect(plan.skipped).toEqual([{ relativePath: '资料库/图片.png', reason: 'unsupported' }])
    expect(plan.totalBytes).toBe(8)
  })

  it('skips a supported file that exceeds the Core single-file limit', () => {
    const oversized = folderFile('资料库/large.pdf')
    Object.defineProperty(oversized, 'size', { value: MAX_SOURCE_BYTES + 1 })

    expect(planFolderImport([oversized]).skipped).toEqual([
      { relativePath: '资料库/large.pdf', reason: 'too-large' }
    ])
  })

  it('blocks a folder with too many supported files', () => {
    const files = Array.from({ length: MAX_FOLDER_FILE_COUNT + 1 }, (_, index) =>
      folderFile(`资料库/${index}.txt`, 0)
    )

    expect(planFolderImport(files).blockedReason).toContain(String(MAX_FOLDER_FILE_COUNT))
  })
})
