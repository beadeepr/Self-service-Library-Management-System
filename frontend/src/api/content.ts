/**
 * 内容类接口：公告、活动、站内通知。
 * 公告与活动公开可读（读者仅见已发布内容），站内通知只返回本人的。
 */
import { get, post, type Page } from './client'

export interface Announcement {
  id: number
  title: string
  body: string
  published: boolean
  created_at: string
  updated_at: string
}

export interface Activity {
  id: number
  branch: number
  title: string
  audience: string
  starts_at: string
  capacity: number
  published: boolean
  created_at: string
  updated_at: string
}

export interface Notification {
  id: number
  reader: number
  title: string
  body: string
  read_at: string | null
  created_at: string
  updated_at: string
}

export function listAnnouncements(params: { page?: number } = {}): Promise<Page<Announcement>> {
  return get<Page<Announcement>>('/announcements/', { params })
}

export function listActivities(params: { page?: number } = {}): Promise<Page<Activity>> {
  return get<Page<Activity>>('/activities/', { params })
}

export function listNotifications(params: { page?: number } = {}): Promise<Page<Notification>> {
  return get<Page<Notification>>('/notifications/', { params })
}

export function markNotificationRead(id: number): Promise<Notification> {
  return post<Notification>(`/notifications/${id}/read/`)
}

export interface Consent {
  id: number
  purpose: 'identity' | 'biometric'
  policy_version: string
  granted: boolean
  reader: number
  created_at: string
  updated_at: string
}

export function listConsents(): Promise<Page<Consent>> {
  return get<Page<Consent>>('/consents/')
}

/**
 * 记录同意/撤回。实名核验前必须先有一条 purpose='identity' 且 granted=true 的记录，
 * 否则后端会拒绝核验请求（policy_version 为必填）。
 */
export function recordConsent(input: { purpose: Consent['purpose']; granted: boolean; policy_version: string }): Promise<Consent> {
  return post<Consent>('/consents/', input)
}
