/**
 * 馆藏接口：书目、副本、分类、网点。
 * 对应 backend/library/api/catalog.py（王恒提供）。
 *
 * 注意书目（Book）与副本（Copy）是两层：库存数量由副本统计得出，
 * 借书接口收的是副本 ID 而不是书目 ID，所以详情页必须能按书目查出副本。
 */
import { get, type Page } from './client'

export type CopyStatus = 'available' | 'loaned' | 'reserved' | 'processing' | 'transit' | 'withdrawn' | 'lost'

/** 副本状态的中文说明，供列表与筛选共用。 */
export const COPY_STATUS_LABEL: Record<CopyStatus, string> = {
  available: '可借',
  loaned: '已借出',
  reserved: '已被预约',
  processing: '待处理',
  transit: '配送中',
  withdrawn: '已下架',
  lost: '遗失',
}

export interface Book {
  id: number
  isbn: string
  title: string
  author: string
  publisher: string
  call_number: string
  /** 十进制定点字符串，如 "59.00" */
  price: string
  cover: string
  active: boolean
  category: number | null
  available_count: number
  total_count: number
  loaned_count: number
  /** 无在架可借副本且已有借出时后端建议预约 */
  can_reserve: boolean
  created_at: string
  updated_at: string
}

export interface Copy {
  id: number
  rfid: string
  shelf: string
  status: CopyStatus
  disinfected_at: string | null
  shelving_due_at: string | null
  book: number
  branch: number
  created_at: string
  updated_at: string
}

export interface Category {
  id: number
  code: string
  name: string
  parent: number | null
  created_at: string
  updated_at: string
}

export interface Branch {
  id: number
  name: string
  address: string
  /** 开闭馆时间相同表示全天开放 */
  opening_time: string
  closing_time: string
  active: boolean
  seats: number
  capacity: number
  area: string
  zones: string[]
  services: string[]
  accessibility: string
  evaluation: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface BranchOccupancy {
  branch: number
  occupancy: number
  capacity: number
  seats: number
  /** 按在馆人数估算的空闲座位，未连接座位传感器 */
  estimated_free_seats: number
}

export interface BookQuery {
  /** 关键词：书名、ISBN、作者、分类号、索书号（后端 SearchFilter） */
  search?: string
  isbn?: string
  category?: number | string
  author?: string
  active?: boolean
  /** 可选 id / title / price，前缀 - 表示倒序 */
  ordering?: string
  page?: number
}

/** 剔除空值，避免把空字符串当作过滤条件发给后端。 */
function clean(params: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  )
}

export function searchBooks(query: BookQuery = {}): Promise<Page<Book>> {
  return get<Page<Book>>('/books/', { params: clean({ ...query }) })
}

export function fetchBook(id: number | string): Promise<Book> {
  return get<Book>(`/books/${id}/`)
}

export function searchCopies(query: { book?: number; branch?: number; status?: CopyStatus; rfid?: string; shelf?: string; page?: number }): Promise<Page<Copy>> {
  return get<Page<Copy>>('/copies/', { params: clean({ ...query }) })
}

export function listCategories(): Promise<Page<Category>> {
  return get<Page<Category>>('/categories/')
}

export function listBranches(): Promise<Page<Branch>> {
  return get<Page<Branch>>('/branches/')
}

/** 在馆人数与估算空闲座位，公开接口。 */
export function fetchBranchOccupancy(id: number | string): Promise<BranchOccupancy> {
  return get<BranchOccupancy>(`/branches/${id}/occupancy/`)
}
