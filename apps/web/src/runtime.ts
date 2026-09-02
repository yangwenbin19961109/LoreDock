import { invoke } from '@tauri-apps/api/core'

export interface CoreConnection {
  readonly baseUrl: string
  readonly token: string
  readonly apiVersion: string
}

declare global {
  interface Window {
    readonly __TAURI_INTERNALS__?: unknown
  }
}

let connection: Promise<CoreConnection | undefined> | undefined

export function coreConnection(): Promise<CoreConnection | undefined> {
  if (!connection) {
    connection =
      typeof window !== 'undefined' && window.__TAURI_INTERNALS__
        ? invoke<CoreConnection>('core_connection')
        : Promise.resolve(undefined)
  }
  return connection
}
