/**
 * 离线交易本地队列，对应 FR-34 的客户端部分（IndexedDB + 幂等去重）。
 *
 * 必须如实说明的边界：
 * - 浏览器/终端的离线本地队列与离线身份授权凭证属于**客户端职责**，
 *   后端只提供补传与冲突处理接口 `/api/offline/sync/`，而该接口**仅管理员可用**。
 *   因此以读者身份操作的自助终端实际上无法自行补传 —— 本模块演示的是
 *   「队列、幂等键、状态回写」这套客户端机制，不声称已打通真实离线借还。
 * - 每笔交易携带全局唯一的 `event_id`，重试必须保持该 ID 与内容不变；
 *   同一 ID 携带不同内容会被后端判为 conflict，需要人工复核。
 * - 补传不是「回放本地结果」：后端仍会重新校验库存与读者资格，冲突不会被覆盖。
 *
 * 后端逐条返回 {event_id, status: 'applied'|'conflict', result|detail}，
 * 批次本身不需要幂等键 —— 去重靠每条的 event_id（offline_idempotent）。
 */
import { post } from '@/api/client'

const DB_NAME = 'library-offline'
const DB_VERSION = 1
const STORE = 'transactions'

export interface OfflineTransaction {
  /** 全局唯一，重试必须保持不变 */
  event_id: string
  kind: 'borrow' | 'return'
  readonly occurred_at: string
  /** 借书需要 */
  reader?: number
  copy?: number
  /** 还书需要 */
  loan?: number
  branch?: number
  /** 本地同步状态，由后端逐条结果回写 */
  sync?: 'pending' | 'applied' | 'conflict'
  message?: string
}

function newEventId(): string {
  const webCrypto = globalThis.crypto
  if (webCrypto && typeof webCrypto.randomUUID === 'function') return webCrypto.randomUUID()
  return `offline-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

/** 本地时间戳带时区偏移，后端要求 occurred_at 为带时区的时间。 */
function localIso(): string {
  const now = new Date()
  const offset = -now.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const pad = (value: number): string => String(Math.floor(Math.abs(value))).padStart(2, '0')
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}` +
    `${sign}${pad(offset / 60)}:${pad(offset % 60)}`
  )
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'event_id' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('无法打开本地数据库'))
  })
}

async function withStore<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await openDb()
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE, mode)
    const request = run(tx.objectStore(STORE))
    request.onsuccess = () => resolve(request.result as T)
    request.onerror = () => reject(request.error ?? new Error('本地队列操作失败'))
    tx.oncomplete = () => db.close()
  })
}

/** 入队一笔交易。返回生成的 event_id，重试时不要重新生成。 */
export async function enqueue(input: Omit<OfflineTransaction, 'event_id' | 'occurred_at' | 'sync'>): Promise<OfflineTransaction> {
  const item: OfflineTransaction = { ...input, event_id: newEventId(), occurred_at: localIso(), sync: 'pending' }
  await withStore('readwrite', (store) => store.put(item))
  return item
}

export async function listQueued(): Promise<OfflineTransaction[]> {
  const items = await withStore<OfflineTransaction[]>('readonly', (store) => store.getAll())
  return items.sort((left, right) => left.occurred_at.localeCompare(right.occurred_at))
}

export async function clearQueued(): Promise<void> {
  await withStore('readwrite', (store) => store.clear())
}

interface SyncResult {
  applied: number
  conflict: number
  pending: number
  /** 后端对未处理项给出的原因 */
  messages: string[]
}

/**
 * 尝试补传队列中的全部交易。
 *
 * 注意权限：后端 `/offline/sync/` 仅管理员可用，读者身份的终端调用会被拒绝（403），
 * 此时本函数把错误原样抛出，由界面如实提示，而不是假装补传成功。
 */
export async function syncNow(): Promise<SyncResult> {
  const transactions = await listQueued()
  if (!transactions.length) return { applied: 0, conflict: 0, pending: 0, messages: [] }

  // 只提交后端需要的字段，本地状态不发给服务端。
  const payload = {
    transactions: transactions.map((item) => {
      const { event_id, kind, occurred_at, reader, copy, loan, branch } = item
      return Object.fromEntries(
        Object.entries({ event_id, kind, occurred_at, reader, copy, loan, branch }).filter(([, value]) => value !== undefined),
      )
    }),
  }

  // 后端逐条返回 {event_id, status, result|detail}；冲突原因是 detail，成功时是 result。
  const data = await post<{ results?: { event_id: string; status: string; result?: unknown; detail?: unknown }[] }>(
    '/offline/sync/',
    payload,
  )
  const results = data?.results ?? []
  const summary: SyncResult = { applied: 0, conflict: 0, pending: 0, messages: [] }

  for (const result of results) {
    const item = transactions.find((entry) => entry.event_id === result.event_id)
    if (!item) continue
    if (result.status === 'applied') {
      summary.applied += 1
      item.sync = 'applied'
      item.message = undefined
    } else {
      summary.conflict += 1
      item.sync = 'conflict'
      const detail = typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail ?? '冲突')
      item.message = detail
      summary.messages.push(detail)
    }
    await withStore('readwrite', (store) => store.put(item))
  }

  // 后端未回执的项保持待处理，不能想当然认为已成功。
  summary.pending = transactions.filter((item) => item.sync === 'pending').length
  return summary
}

export const offlineQueue = { enqueue, listQueued, clearQueued, syncNow }
