import { invoke } from '@tauri-apps/api/core'

export interface CoreConnection {
  readonly baseUrl: string
  readonly token: string
  readonly apiVersion: string
}

export type DesktopCoreState = 'starting' | 'ready' | 'recovering' | 'failed' | 'stopped'

export interface DesktopCoreStatus {
  readonly state: DesktopCoreState
  readonly errorCode?: string | null
  readonly message?: string | null
  readonly restartCount: number
}

declare global {
  interface Window {
    readonly __TAURI_INTERNALS__?: unknown
  }
}

function isTauri(): boolean {
  return typeof window !== 'undefined' && Boolean(window.__TAURI_INTERNALS__)
}

export function coreConnection(): Promise<CoreConnection | undefined> {
  return isTauri() ? invoke<CoreConnection>('core_connection') : Promise.resolve(undefined)
}

export function desktopCoreStatus(): Promise<DesktopCoreStatus | undefined> {
  return isTauri() ? invoke<DesktopCoreStatus>('core_status') : Promise.resolve(undefined)
}

export async function restartDesktopCore(): Promise<void> {
  if (!isTauri()) throw new Error('只有桌面应用可以重新启动 Core。')
  await invoke('restart_core')
}
