import { useEffect, useState } from 'react'
import { Button } from '@loredock/ui'
import { activityApi } from './activityApi'

export function FavoriteButton({
  sourceId,
  onChange
}: {
  readonly sourceId: string
  readonly onChange?: () => void
}) {
  const [favorite, setFavorite] = useState<boolean>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    void activityApi
      .favorite(sourceId, controller.signal)
      .then(setFavorite)
      .catch(() => {
        if (!controller.signal.aborted) setError('无法读取收藏状态，请重试。')
      })
    return () => controller.abort()
  }, [sourceId, retry])
  async function toggle() {
    if (busy || favorite === undefined) return
    setBusy(true)
    setError('')
    try {
      setFavorite(await activityApi.setFavorite(sourceId, !favorite))
      onChange?.()
    } catch {
      setError('收藏更新未确认，请重试。')
      setFavorite(undefined)
      setRetry((value) => value + 1)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="favorite-action">
      <Button
        variant="ghost"
        className="favorite-star"
        disabled={busy || favorite === undefined}
        aria-pressed={favorite ?? false}
        aria-label={busy ? '正在保存收藏' : favorite ? '取消收藏' : '收藏资料'}
        title={favorite ? '取消收藏' : '收藏资料'}
        onClick={() => void toggle()}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="m12 2.75 2.8 5.68 6.27.91-4.54 4.43 1.07 6.25L12 17.07l-5.6 2.95 1.07-6.25-4.54-4.43 6.27-.91L12 2.75Z" />
        </svg>
      </Button>
      {error && (
        <>
          <span role="alert">{error}</span>
          <Button
            variant="ghost"
            onClick={() => {
              setError('')
              setRetry((value) => value + 1)
            }}
          >
            重试收藏状态
          </Button>
        </>
      )}
    </div>
  )
}
