/** 与后端一致的前端预校验，避免无谓请求；最终校验始终以后端为准。 */

/** 对齐后端 PhoneSerializer 的 ^1\d{10}$。 */
export const PHONE_PATTERN = /^1\d{10}$/

export function isPhone(value: string): boolean {
  return PHONE_PATTERN.test(value)
}

/**
 * 对齐后端 Django 密码校验器可前端预判的部分：MinimumLengthValidator 与 NumericPasswordValidator。
 * CommonPasswordValidator 与相似度校验只能由后端给出，因此这里只拦明显不合格的输入。
 */
export function passwordProblem(password: string): string | null {
  if (password.length < 8) return '密码至少 8 位'
  if (/^\d+$/.test(password)) return '密码不能全为数字'
  return null
}
