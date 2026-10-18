/**
 * 罚款与支付接口，对应 backend/library/api/fines.py。
 *
 * 罚款由后端维护任务按天累计（不足一天按一天），费率来自借阅规则。
 * 支付分两步：先按未付余额创建订单（幂等），再模拟/线下结算；
 * 重复下同一笔已缴清的罚款会被后端拒绝（「罚款已缴清」）。
 *
 * 未缴清罚款会阻止读者继续借阅（后端 eligible 里与逾期、信用、冻结并列判断），
 * 所以缴款不只是记账，而是恢复借阅资格的前置条件之一。逾期未还也一样会拦截。
 */
import { get, post, postIdempotent, type Page } from './client'

export interface Fine {
  id: number
  loan: number
  /** 累计应缴金额，两位小数字符串 */
  amount: string
  paid_amount: string
  /** 已计费天数 */
  assessed_days: number
  created_at: string
  updated_at: string
}

export type PaymentStatus = 'pending' | 'paid'

export interface Payment {
  id: number
  reference: string
  reader: number
  fine: number
  amount: string
  status: PaymentStatus
  paid_at: string | null
  created_at: string
  updated_at: string
}

export function listFines(params: { page?: number } = {}): Promise<Page<Fine>> {
  return get<Page<Fine>>('/fines/', { params })
}

export function listPayments(params: { page?: number } = {}): Promise<Page<Payment>> {
  return get<Page<Payment>>('/payments/', { params })
}

/** 按未付余额创建支付订单。金额由后端计算，前端不参与。 */
export function createPayment(fine: number, key: string): Promise<Payment> {
  return postIdempotent<Payment>('/payments/', { fine }, key)
}

/**
 * 模拟支付。后端按订单状态结算，重复调用不会重复入账，因此这里不需要幂等键。
 * 真实支付供应商尚未接入，未配置时后端会拒绝。
 */
export function simulatePayment(id: number): Promise<Payment> {
  return post<Payment>(`/payments/${id}/simulate/`)
}

/** 未结清金额；后端用 amount 与 paid_amount 两个字段表达进度。 */
export function unpaidAmount(fine: Fine): number {
  const amount = Number(fine.amount)
  const paid = Number(fine.paid_amount)
  if (Number.isNaN(amount) || Number.isNaN(paid)) return 0
  return Math.max(0, Number((amount - paid).toFixed(2)))
}

export function isSettled(fine: Fine): boolean {
  return unpaidAmount(fine) <= 0
}
