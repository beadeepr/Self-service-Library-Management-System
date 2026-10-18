/**
 * 流通接口：借书、还书、续借、借阅历史与借阅规则。
 * 对应 backend/library/api/circulation.py 与 rules.py。
 *
 * 幂等键的语义（后端约定，务必遵守）：同一次交易重试要复用同一个键和相同的请求体，
 * 新交易必须换新键。因此调用方在「确认」这一步生成键并保留，重试时传回来，
 * 而不是每次请求都新生成一个 —— 否则网络抖动重试会变成重复借书。
 */
import { get, post, postIdempotent, type Page } from './client'
import type { CopyStatus } from './books'

export interface Loan {
  id: number
  copy: number
  reader: number
  borrowed_at: string
  due_at: string
  returned_at: string | null
  renewals: number
  /** 有效借阅的唯一副本约束字段，等同于 copy；归还后由后端清空 */
  active_copy: number | null
  created_at: string
  updated_at: string
}

export interface BorrowResult {
  id: number
  copy: number
  due_at: string
}

export interface RenewResult {
  id: number
  due_at: string
  renewals: number
}

export interface ReturnResult {
  id: number
  /** 归还后通常进入 processing，需消毒上架后才可再次外借 */
  copy_status: CopyStatus
  /** 本次归还产生的罚款金额，未逾期为 "0.00" */
  fine: string
}

export interface LoanRules {
  id: number
  name: string
  loan_days: number
  loan_limit: number
  renewal_limit: number
  /** 每天罚款金额，两位小数字符串 */
  fine_per_day: string
  /** 预约到馆保留天数 */
  hold_days: number
  minimum_credit: number
  /** 归还后是否需要消毒上架才可外借 */
  disinfection_required: boolean
  /** 实名读者的借期，未实名用 loan_days */
  verified_loan_days: number
  /** 实名读者的可借上限，未实名用 loan_limit */
  verified_loan_limit: number
  reservation_limit: number
  reservation_deposit: string
  shelving_hours: number
  response_hours: number
  offline_minutes: number
  retention_days: number
  financial_retention_days: number
  /** 节假日日期列表，命中则新借阅与续借的应还日顺延 */
  holidays: string[]
  created_at: string
  updated_at: string
}

export interface LoanQuery {
  /** true 查当前在借，false 查已归还 */
  'returned_at__isnull'?: boolean
  /** 应还日期早于该时间，用于查逾期 */
  'due_at__lt'?: string
  copy?: number
  reader?: number
  page?: number
  ordering?: string
}

export function listLoans(query: LoanQuery = {}): Promise<Page<Loan>> {
  const params = Object.fromEntries(Object.entries(query).filter(([, value]) => value !== undefined && value !== ''))
  return get<Page<Loan>>('/loans/', { params })
}

export function fetchLoan(id: number | string): Promise<Loan> {
  return get<Loan>(`/loans/${id}/`)
}

/** 借书。读者本人借阅不需要传 reader，仅管理员代借时才指定。 */
export function borrowCopy(copy: number, key: string, reader?: number): Promise<BorrowResult> {
  return postIdempotent<BorrowResult>('/loans/borrow/', reader ? { copy, reader } : { copy }, key)
}

/** 还书。支持跨馆归还，branch 为实际归还网点。 */
export function returnLoan(loan: number, branch: number, damaged: boolean, key: string): Promise<ReturnResult> {
  return postIdempotent<ReturnResult>(`/loans/${loan}/return/`, { branch, damaged }, key)
}

/** 续借。受逾期、预约队列、续借次数与欠费校验限制，失败原因由后端给出。 */
export function renewLoan(loan: number, key: string): Promise<RenewResult> {
  return postIdempotent<RenewResult>(`/loans/${loan}/renew/`, {}, key)
}

/** 当前生效的借阅规则，登录即可读；修改仅限管理员。 */
export function fetchRules(): Promise<LoanRules> {
  return get<LoanRules>('/rules/current/')
}

/** 站内催还，仅管理员。通知发到读者站内信，不涉及外部通道。 */
export function remindLoan(loan: number): Promise<{ sent: boolean; channel: string }> {
  return post<{ sent: boolean; channel: string }>(`/loans/${loan}/remind/`)
}
