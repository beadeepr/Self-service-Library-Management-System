/** 认证接口，对应 backend/library/api/auth.py（王恒提供）。 */
import { get, post } from './client'
import type { Role } from './session'

/** 短信验证码用途，对应 CodeRequestSerializer 的 purpose 取值。 */
export type SmsPurpose = 'register' | 'login' | 'phone'

export interface TokenPayload {
  access: string
  refresh: string
  role: Role
}

export interface UserProfile {
  id: number
  phone: string
  first_name: string
  /** 后端为 blank=True 的非空字段，空值形态是空字符串而不是 null */
  avatar: string
  contact: string
  role: Role
  verified: boolean
  credit: number
  credit_level: 'normal' | 'restricted' | 'untrusted'
  frozen: boolean
  deposit: string
  is_active: boolean
}

export interface CaptchaPayload {
  captcha_id: string
  /** data:image/svg+xml;base64,... 可直接放进 img src。 */
  image: string
  expires_in: number
}

export interface SmsCodePayload {
  expires_in: number
  simulation: boolean
  /** 仅模拟模式返回，供演示时直接填表；真实环境不存在该字段。 */
  simulation_code?: string
}

export function fetchCaptcha(): Promise<CaptchaPayload> {
  return get<CaptchaPayload>('/auth/captcha/')
}

export function sendSmsCode(input: {
  phone: string
  purpose: SmsPurpose
  captcha_id: string
  captcha_answer: string
}): Promise<SmsCodePayload> {
  return post<SmsCodePayload>('/auth/sms-code/', input)
}

export function login(phone: string, password: string): Promise<TokenPayload> {
  return post<TokenPayload>('/auth/login/', { phone, password })
}

export function smsLogin(phone: string, code: string): Promise<TokenPayload> {
  return post<TokenPayload>('/auth/sms-login/', { phone, code })
}

export function register(input: {
  phone: string
  code: string
  password: string
  first_name?: string
}): Promise<UserProfile> {
  return post<UserProfile>('/auth/register/', input)
}

/** 吊销刷新令牌；已签发的 access 在到期前仍然有效（后端约定）。 */
export function logout(refresh: string): Promise<null> {
  return post<null>('/auth/logout/', { refresh })
}

/** 扫码登录：终端展示二维码，读者在已登录的 Web 端确认。 */
export function createQrChallenge(): Promise<{ token: string; poll_secret: string; expires_in: number }> {
  return post('/auth/qr-challenge/')
}

export function confirmQrChallenge(token: string): Promise<{ confirmed: boolean }> {
  return post('/auth/qr-confirm/', { token })
}

export function pollQrChallenge(token: string, poll_secret: string): Promise<Partial<TokenPayload> & { status?: string }> {
  return post('/auth/qr-poll/', { token, poll_secret })
}
