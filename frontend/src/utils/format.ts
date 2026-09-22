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
