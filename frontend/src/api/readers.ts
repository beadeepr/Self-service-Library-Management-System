/** 读者资料与管理接口，对应 backend/library/api/readers.py（王恒提供）。 */
import { get, patch, post, postIdempotent, type Page } from './client'
import type { UserProfile } from './auth'
import type { Role } from './session'

export interface CreditEntry {
  id: number
  delta: number
  balance: number
  reason: string
  created_at: string
}

export interface DepositEntry {
  id: number
  delta: string
  balance: string
  reason: string
  created_at: string
}

export function fetchMe(): Promise<UserProfile> {
  return get<UserProfile>('/readers/me/')
}

export function updateMe(input: Pick<UserProfile, 'first_name' | 'avatar' | 'contact'>): Promise<UserProfile> {
  return patch<UserProfile>('/readers/me/', input)
}

/** 模拟实名核验：仅校验 18 位格式与唯一性，不代表已完成公安核验。 */
export function verifyIdentity(identity: string): Promise<UserProfile> {
  return post<UserProfile>('/readers/verify-identity/', { identity })
}

/** 修改后旧 access 立即失效（后端会做令牌校验），需重新登录。 */
export function changePassword(old_password: string, new_password: string): Promise<{ detail: string }> {
  return post<{ detail: string }>('/readers/password/', { old_password, new_password })
}

/** 换号需要向新手机号发送 purpose='phone' 的验证码。 */
export function changePhone(phone: string, code: string): Promise<UserProfile> {
  return post<UserProfile>('/readers/phone/', { phone, code })
}

export function listReaders(params?: Record<string, unknown>): Promise<Page<UserProfile>> {
  return get<Page<UserProfile>>('/readers/', { params })
}

export interface ReaderManageInput {
  reason: string
  frozen?: boolean
  role?: Role
  credit_delta?: number
  deposit_delta?: string
  new_password?: string
}

/** 管理员操作，幂等：冻结、重置密码、信用与押金增减；role 仅超级管理员可改。 */
export function manageReader(id: number, input: ReaderManageInput, key?: string): Promise<Partial<UserProfile>> {
  return postIdempotent(`/readers/${id}/manage/`, input, key)
}

export function listCreditEntries(params?: Record<string, unknown>): Promise<Page<CreditEntry>> {
  return get<Page<CreditEntry>>('/credit-entries/', { params })
}

export function listDepositEntries(params?: Record<string, unknown>): Promise<Page<DepositEntry>> {
  return get<Page<DepositEntry>>('/deposit-entries/', { params })
}
