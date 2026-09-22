/**
 * 统一 HTTP 客户端。
 *
 * 后端约定（见 backend/docs/API.md）：
 * - 响应恒为 {code, message, data, request_id}，成功 code=0；HTTP 200 不代表业务成功。
 * - 库存不可借返回 HTTP 200 + code=4001，必须按业务码判断。
 * - 列表分页数据在 data.results。
 * - 借还、续借、预约、支付、门禁读卡为幂等操作，必须带 Idempotency-Key。
 *
 * 本模块负责三件事，页面不再重复实现：解包信封并判 code、401 单飞刷新重试、幂等键生成。
 */
import axios, { AxiosError, type AxiosRequestConfig, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { clearSession, getAccessToken, getRefreshToken, saveSession } from './session'

export const API_BASE = '/api/v1'

/** 库存不可借：后端约定 HTTP 200 + code 4001。 */
export const CODE_OUT_OF_STOCK = 4001

/** 分页响应体，位于信封的 data 字段。 */
export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

interface Envelope<T> {
  code: number
  message: string
  data: T
  request_id?: string
}

export class ApiError extends Error {
  readonly code: number
  readonly status: number
  readonly data: unknown
  readonly requestId?: string

  constructor(code: number, message: string, options: { status?: number; data?: unknown; requestId?: string } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = options.status ?? 200
    this.data = options.data
    this.requestId = options.requestId
  }

  get isOutOfStock(): boolean {
    return this.code === CODE_OUT_OF_STOCK
  }

  get isAuthFailure(): boolean {
    return this.status === 401 || this.status === 403 || this.code === 40100 || this.code === 40300
  }
}

function isEnvelope(value: unknown): value is Envelope<unknown> {
  return !!value && typeof value === 'object' && 'code' in value && 'data' in value
}

/**
 * 由响应体推导可读的失败原因。
 * 后端 message 在存在 detail 时即为该 detail，校验错误则放在 data 里（形如 {字段: ["消息"]}）。
 */
function describeError(envelope: Envelope<unknown> | undefined, fallback: string): string {
  if (!envelope) return fallback
  const data = envelope.data
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail) return detail
    for (const value of Object.values(data as Record<string, unknown>)) {
      if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
      if (typeof value === 'string' && value) return value
    }
  }
  return envelope.message && envelope.message !== 'ok' ? envelope.message : fallback
}

const http = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const access = getAccessToken()
  if (access) config.headers.Authorization = `Bearer ${access}`
  return config
})

/** 刷新接口在 401 之外的失败（例如 refresh 已过期被吊销）会让整个会话作废。 */
function expireSession(): void {
  clearSession()
  const { pathname, search, hash } = window.location
  if (pathname === '/reader/login' || pathname === '/login') return
  const redirect = encodeURIComponent(pathname + search + hash)
  // 整页跳转而非 router.push：确保清空所有内存态，避免残留旧身份的页面状态。
  window.location.assign(`/reader/login?expired=1&redirect=${redirect}`)
}

let refreshInFlight: Promise<string> | null = null

async function requestRefresh(): Promise<string> {
  const refresh = getRefreshToken()
  if (!refresh) throw new Error('缺少刷新令牌')
  // 用裸 axios，避免再次进入本实例的拦截器造成递归。
  const response = await axios.post<Envelope<{ access: string; refresh?: string }>>(
    `${API_BASE}/auth/refresh/`,
    { refresh },
    { headers: { 'Content-Type': 'application/json' }, timeout: 15000 },
  )
  const envelope = response.data
  if (!isEnvelope(envelope) || envelope.code !== 0) throw new Error('刷新令牌被拒绝')
  const data = envelope.data as { access: string; refresh?: string }
  saveSession({ access: data.access, refresh: data.refresh ?? refresh })
  return data.access
}

/** 单飞：并发请求同时遇到 401 时只发一次刷新，其余请求复用同一个 Promise。 */
function refreshAccessToken(): Promise<string> {
  if (!refreshInFlight) {
    refreshInFlight = requestRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

http.interceptors.response.use(
  (response: AxiosResponse) => {
    // CSV 导出等非 JSON 响应没有信封，直接透传。
    if (response.config.responseType === 'blob' || response.config.responseType === 'arraybuffer') return response.data
    const envelope: unknown = response.data
    if (!isEnvelope(envelope)) return envelope
    if (envelope.code !== 0) {
      return Promise.reject(
        new ApiError(envelope.code, describeError(envelope, '请求未完成'), {
          status: response.status,
          data: envelope.data,
          requestId: envelope.request_id,
        }),
      )
    }
    return envelope.data
  },
  async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & { _retriedAuth?: boolean }) | undefined
    const response = error.response

    // 无响应：网络中断、跨域失败或超时，后端没有返回信封。
    if (!response) {
      const timeout = error.code === 'ECONNABORTED'
      return Promise.reject(
        new ApiError(-1, timeout ? '请求超时，请重试' : '无法连接服务器，请确认后端已启动', { status: 0 }),
      )
    }

    const payload: unknown = response.data
    const envelope = isEnvelope(payload) ? payload : undefined

    if (response.status === 401 && config && !config._retriedAuth && !String(config.url).includes('/auth/refresh/')) {
      config._retriedAuth = true
      try {
        const access = await refreshAccessToken()
        config.headers.Authorization = `Bearer ${access}`
        return http.request(config)
      } catch {
        expireSession()
      }
    }

    return Promise.reject(
      new ApiError(envelope?.code ?? response.status * 100, describeError(envelope, `请求失败（HTTP ${response.status}）`), {
        status: response.status,
        data: envelope?.data ?? payload,
        requestId: envelope?.request_id,
      }),
    )
  },
)

/**
 * 幂等键。借还、续借、预约、支付、门禁读卡必须携带；
 * 同一笔交易重试要复用同一个键，新交易生成新键。
 */
export function newIdempotencyKey(): string {
  const webCrypto = globalThis.crypto
  if (webCrypto && typeof webCrypto.randomUUID === 'function') return webCrypto.randomUUID()
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

// 以下封装把解包后的 data 直接作为返回值类型，页面调用处无需再处理 AxiosResponse。
export function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return http.get(url, config) as unknown as Promise<T>
}

export function post<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return http.post(url, body, config) as unknown as Promise<T>
}

export function put<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return http.put(url, body, config) as unknown as Promise<T>
}

export function patch<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return http.patch(url, body, config) as unknown as Promise<T>
}

export function del<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return http.delete(url, config) as unknown as Promise<T>
}

/** 幂等写操作。重试同一笔交易时传入上一次的 key，避免重复借还或重复入账。 */
export function postIdempotent<T>(url: string, body?: unknown, key?: string, config: AxiosRequestConfig = {}): Promise<T> {
  return post<T>(url, body, {
    ...config,
    headers: { ...config.headers, 'Idempotency-Key': key ?? newIdempotencyKey() },
  })
}

export default http
