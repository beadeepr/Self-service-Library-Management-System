/**
 * 令牌与身份的最小持久化层。
 *
 * 单独成文件是为了断开循环依赖：api/client.ts 需要在拦截器里读令牌，
 * stores/auth.ts 也需要读写令牌，若令牌状态只放在 Pinia store 里，
 * client.ts 就必须反向 import store，形成 client → store → api/auth → client 的环。
 * 这里不依赖 Vue，两侧都只依赖它。
 *
 * 存储介质为 localStorage：自助终端刷新页面后仍需保持借阅会话。
 * 代价是令牌对 XSS 可见，课程演示可接受；生产环境应改为 HttpOnly Cookie。
 */
export type Role = 'reader' | 'admin' | 'operator'

const ACCESS_KEY = 'library.access'
const REFRESH_KEY = 'library.refresh'
const ROLE_KEY = 'library.role'

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* 隐私模式下不可写，退化为内存会话（刷新即失效） */
  }
}

function drop(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* 同上 */
  }
}

export function getAccessToken(): string | null {
  return read(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return read(REFRESH_KEY)
}

export function getStoredRole(): Role | null {
  const role = read(ROLE_KEY)
  return role === 'reader' || role === 'admin' || role === 'operator' ? role : null
}

/**
 * 保存令牌。刷新接口开启了轮换（ROTATE_REFRESH_TOKENS），
 * 响应会同时返回新的 refresh，必须覆盖旧值，否则旧令牌已进黑名单。
 */
export function saveSession(input: { access: string; refresh?: string; role?: Role }): void {
  write(ACCESS_KEY, input.access)
  if (input.refresh) write(REFRESH_KEY, input.refresh)
  if (input.role) write(ROLE_KEY, input.role)
}

export function clearSession(): void {
  drop(ACCESS_KEY)
  drop(REFRESH_KEY)
  drop(ROLE_KEY)
}
