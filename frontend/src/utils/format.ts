/** 展示层格式化。后端时间是带时区的 ISO-8601，金额是两位小数字符串。 */

const DATE = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
const DATE_TIME = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function toDate(value: string): Date | null {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? DATE.format(date) : '—'
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = toDate(value)
  return date ? DATE_TIME.format(date) : '—'
}

/** 金额已在后端以定点字符串返回，这里只做展示与补符号。 */
export function formatMoney(value?: string | number | null): string {
  if (value === null || value === undefined || value === '') return '—'
  const amount = Number(value)
  return Number.isNaN(amount) ? String(value) : `¥${amount.toFixed(2)}`
}

/**
 * 距离目标日期的天数：0 表示就是今天，负数表示已过期。
 * 按自然日比较而不是毫秒差，否则「今天 23:00 到期」在同一天上午会算成 0 天但下午变成负值。
 */
export function daysUntil(target: string, now: Date = new Date()): number {
  const targetDate = toDate(target)
  if (!targetDate) return 0
  const startOfDay = (value: Date): number => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
  return Math.round((startOfDay(targetDate) - startOfDay(now)) / 86_400_000)
}

/**
 * 应还日期的可读提示。
 *
 * 逾期天数刻意采用与后端计费一致的口径：按已过时长向上取整（「不足一天按一天」，
 * 见 fine_service.assess_fine 的 ceil）。若这里改用整日历天数，会出现
 * 「页面显示逾期 10 天、罚款按 11 天收」的错位 —— 演示与答疑时都会成为问题。
 * 未逾期时仍按自然日显示剩余天数，符合读者直觉。
 */
export function dueDescription(due: string): { text: string; overdue: boolean } {
  const dueDate = toDate(due)
  if (!dueDate) return { text: '—', overdue: false }
  const now = new Date()
  if (now.getTime() > dueDate.getTime()) {
    const overdueDays = Math.max(1, Math.ceil((now.getTime() - dueDate.getTime()) / 86_400_000))
    return { text: `已逾期 ${overdueDays} 天`, overdue: true }
  }
  const days = daysUntil(due, now)
  if (days === 0) return { text: '今天到期', overdue: false }
  return { text: `剩余 ${days} 天`, overdue: false }
}
