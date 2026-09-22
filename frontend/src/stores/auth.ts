/**
 * 登录态。令牌本身存在 api/session.ts（供 client.ts 拦截器读取），
 * 这里只维护响应式副本与登录/登出动作，避免出现两份令牌真相。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'
import { clearSession, getAccessToken, getRefreshToken, getStoredRole, saveSession, type Role } from '@/api/session'

export const useAuthStore = defineStore('auth', () => {
  const access = ref<string | null>(getAccessToken())
  const role = ref<Role | null>(getStoredRole())

  const isAuthenticated = computed(() => !!access.value)
  const isReader = computed(() => role.value === 'reader')
  const isAdmin = computed(() => role.value === 'admin')
  const isOperator = computed(() => role.value === 'operator')

  function applySession(payload: { access: string; refresh?: string; role?: Role }): void {
    saveSession(payload)
    access.value = payload.access
    if (payload.role) role.value = payload.role
  }

  async function login(phone: string, password: string): Promise<void> {
    applySession(await authApi.login(phone, password))
  }

  async function loginBySms(phone: string, code: string): Promise<void> {
    applySession(await authApi.smsLogin(phone, code))
  }

  /** 扫码登录与自助终端读者签到拿到令牌后，统一从这里写入登录态。 */
  function adoptSession(payload: { access: string; refresh?: string; role?: Role }): void {
    applySession(payload)
  }

  /** 只清本地，不调后端。令牌已失效或刷新被拒时使用。 */
  function forget(): void {
    clearSession()
    access.value = null
    role.value = null
  }

  async function logout(): Promise<void> {
    const refresh = getRefreshToken()
    try {
      if (refresh) await authApi.logout(refresh)
    } catch {
      // 吊销失败（网络或令牌已过期）不应阻止用户登出，本地状态照常清理。
    }
    forget()
  }

  function hasRole(...roles: Role[]): boolean {
    return !!role.value && roles.includes(role.value)
  }

  /** 角色默认落点：读者回读者端，管理员与运维共用管理后台。 */
  function homePath(): string {
    return role.value === 'reader' ? '/reader/home' : '/admin/dashboard'
  }

  return {
    access,
    role,
    isAuthenticated,
    isReader,
    isAdmin,
    isOperator,
    login,
    loginBySms,
    adoptSession,
    forget,
    logout,
    hasRole,
    homePath,
  }
})
