/**
 * 预约接口：预约、取消、取书。对应 backend/library/api/reservations.py。
 *
 * 状态机（后端）：waiting → ready → collected，waiting/ready 可取消，超时未取转 expired。
 * 关键点：waiting 时 copy 与 expires_at 都是 null，只有在「有副本上架时被分配」之后
 * （后端 assign_hold）才会写入副本与保留截止时间，也才有到馆通知。
 * 因此前端不能假设预约一创建就有副本或保留期。
 *
 * 取书（collect）在后端等价于预约持有者借出那个保留副本，会生成一条借阅记录，
 * 并且只有 status='ready' 时才允许。
 */
import { get, postIdempotent, type Page } from './client'
import type { BorrowResult } from './circulation'

export type ReservationStatus = 'waiting' | 'ready' | 'collected' | 'cancelled' | 'expired'

export const RESERVATION_STATUS_LABEL: Record<ReservationStatus, string> = {
  waiting: '排队中',
  ready: '已到馆待取',
  collected: '已取书',
  cancelled: '已取消',
  expired: '已过期',
}

export interface Reservation {
  id: number
  reader: number
  book: number
  branch: number
  /** 仅在 ready 及之后才有值 */
  copy: number | null
  status: ReservationStatus
  /** 到馆保留截止时间，waiting 阶段为 null */
  expires_at: string | null
  created_at: string
  updated_at: string
}

export interface ReservationQuery {
  status?: ReservationStatus
  book?: number
  branch?: number
  page?: number
}

export function listReservations(query: ReservationQuery = {}): Promise<Page<Reservation>> {
  const params = Object.fromEntries(Object.entries(query).filter(([, value]) => value !== undefined && value !== ''))
  return get<Page<Reservation>>('/reservations/', { params })
}

/** 预约某书目的某网点取书。后端会校验该网点确实无可借副本、且未重复预约。 */
export function createReservation(book: number, branch: number, key: string): Promise<Reservation> {
  return postIdempotent<Reservation>('/reservations/', { book, branch }, key)
}

/** 取消预约，waiting 与 ready 均可取消。 */
export function cancelReservation(id: number, key: string): Promise<Reservation> {
  return postIdempotent<Reservation>(`/reservations/${id}/cancel/`, {}, key)
}

/** 到馆取书。仅 status='ready' 可用，成功后在返回结果里给出新建的借阅记录。 */
export function collectReservation(id: number, key: string): Promise<BorrowResult> {
  return postIdempotent<BorrowResult>(`/reservations/${id}/collect/`, {}, key)
}
