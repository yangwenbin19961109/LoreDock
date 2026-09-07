export const SUPPORTED_SOURCE_SUFFIXES = new Set([
  '.md',
  '.markdown',
  '.txt',
  '.pdf',
  '.docx',
  '.pptx',
  '.xlsx',
  '.htm',
  '.html'
])

export const MAX_FOLDER_FILE_COUNT = 500
export const MAX_FOLDER_TOTAL_BYTES = 1024 * 1024 * 1024
export const MAX_SOURCE_BYTES = 100 * 1024 * 1024

export interface FolderImportFile {
  readonly file: File
  readonly relativePath: string
}

export interface SkippedFolderFile {
  readonly relativePath: string
  readonly reason: 'unsupported' | 'too-large'
}

export interface FolderImportPlan {
  readonly folderName: string
  readonly files: readonly FolderImportFile[]
  readonly skipped: readonly SkippedFolderFile[]
  readonly totalBytes: number
  readonly blockedReason?: string
}

function suffixOf(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot < 0 ? '' : filename.slice(dot).toLowerCase()
}

function normalizedRelativePath(file: File): string {
  const candidate = file.webkitRelativePath || file.name
  return candidate.replaceAll('\\', '/').replace(/^\/+/, '')
}

export function planFolderImport(selectedFiles: Iterable<File>): FolderImportPlan {
  const files: FolderImportFile[] = []
  const skipped: SkippedFolderFile[] = []

  for (const file of selectedFiles) {
    const relativePath = normalizedRelativePath(file)
    if (!SUPPORTED_SOURCE_SUFFIXES.has(suffixOf(file.name))) {
      skipped.push({ relativePath, reason: 'unsupported' })
      continue
    }
    if (file.size > MAX_SOURCE_BYTES) {
      skipped.push({ relativePath, reason: 'too-large' })
      continue
    }
    files.push({ file, relativePath })
  }

  files.sort((left, right) => left.relativePath.localeCompare(right.relativePath, 'zh-CN'))
  skipped.sort((left, right) => left.relativePath.localeCompare(right.relativePath, 'zh-CN'))
  const totalBytes = files.reduce((sum, item) => sum + item.file.size, 0)
  const folderName =
    (files[0]?.relativePath ?? skipped[0]?.relativePath ?? '').split('/')[0] || '所选文件夹'
  let blockedReason: string | undefined
  if (files.length > MAX_FOLDER_FILE_COUNT) {
    blockedReason = `可导入文件超过 ${MAX_FOLDER_FILE_COUNT} 份，请缩小选择范围后重试。`
  } else if (totalBytes > MAX_FOLDER_TOTAL_BYTES) {
    blockedReason = '可导入文件总体积超过 1 GiB，请缩小选择范围后重试。'
  }

  return { folderName, files, skipped, totalBytes, blockedReason }
}
