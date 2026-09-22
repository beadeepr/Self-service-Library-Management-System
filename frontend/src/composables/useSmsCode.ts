/**
 * 图形验证码 + 短信验证码的取码流程，登录、注册、个人中心换号三处共用。
 *
 * 流程固定且不可颠倒：先过图形验证码，后端才发短信码。两个要点：
 * 1. 图形验证码是**一次性**的（后端取码时即从缓存删除），所以无论成败都要换一张；
 * 2. 模拟模式下后端直接返回验证码，由调用方决定填到哪个输入框，页面要明确标注是模拟。
 */
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchCaptcha, sendSmsCode, type CaptchaPayload, type SmsPurpose } from '@/api/auth'
import { errorMessage } from '@/api/client'
import { isPhone } from '@/utils/validators'

export function useSmsCode(purpose: SmsPurpose) {
  const captcha = ref<CaptchaPayload | null>(null)
  const captchaAnswer = ref('')
  const captchaLoading = ref(false)
  const sending = ref(false)
  const countdown = ref(0)
  let timer: number | undefined

  function stopCountdown(): void {
    if (timer !== undefined) window.clearInterval(timer)
    timer = undefined
  }

  // 组件卸载时必须清掉定时器，否则离开页面后仍在跑。
  onBeforeUnmount(stopCountdown)

  async function refreshCaptcha(): Promise<void> {
    captchaLoading.value = true
    try {
      captcha.value = await fetchCaptcha()
      captchaAnswer.value = ''
    } catch (error) {
      ElMessage.error(errorMessage(error, '图形验证码加载失败'))
    } finally {
      captchaLoading.value = false
    }
  }

  function startCountdown(seconds = 60): void {
    countdown.value = seconds
    stopCountdown()
    timer = window.setInterval(() => {
      countdown.value -= 1
      if (countdown.value <= 0) stopCountdown()
    }, 1000)
  }

  /**
   * 取短信验证码。onCode 用于把模拟模式的验证码直接填进表单。
   * 返回是否发送成功，调用方据此决定后续流程。
   */
  async function sendCode(phone: string, onCode?: (code: string) => void): Promise<boolean> {
    if (!isPhone(phone)) {
      ElMessage.warning('请先填写 11 位手机号')
      return false
    }
    if (!captcha.value) {
      await refreshCaptcha()
      return false
    }
    if (!captchaAnswer.value) {
      ElMessage.warning('请先填写图形验证码')
      return false
    }

    sending.value = true
    try {
      const payload = await sendSmsCode({
        phone,
        purpose,
        captcha_id: captcha.value.captcha_id,
        captcha_answer: captchaAnswer.value,
      })
      if (payload.simulation_code && onCode) {
        onCode(payload.simulation_code)
        ElMessage.success(`模拟模式：验证码 ${payload.simulation_code} 已自动填入`)
      } else {
        ElMessage.success('验证码已发送，5 分钟内有效')
      }
      startCountdown()
      return true
    } catch (error) {
      ElMessage.error(errorMessage(error, '验证码发送失败'))
      return false
    } finally {
      sending.value = false
      captchaAnswer.value = ''
      // 图形验证码已被后端消费，无论成败都换新的一张。
      await refreshCaptcha()
    }
  }

  return {
    captcha,
    captchaAnswer,
    captchaLoading,
    sending,
    countdown,
    refreshCaptcha,
    sendCode,
  }
}
