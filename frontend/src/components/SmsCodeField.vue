<script setup lang="ts">
/**
 * 图形验证码 + 短信验证码的组合输入项，被登录、注册、换号三处复用。
 *
 * 内部自持取码状态（图形码、倒计时、发送中），外部只需要 :phone 与 v-model:code。
 * 外层 el-form 通过 provide/inject 与这里的 el-form-item 关联，因此短信码
 * 仍参与表单校验，校验路径为父表单模型上的 code 字段。
 */
import { onMounted } from 'vue'
import type { SmsPurpose } from '@/api/auth'
import { useSmsCode } from '@/composables/useSmsCode'

const props = defineProps<{
  phone: string
  purpose: SmsPurpose
  code: string
}>()

const emit = defineEmits<{ 'update:code': [string] }>()

const { captcha, captchaAnswer, captchaLoading, sending, countdown, refreshCaptcha, sendCode } =
  useSmsCode(props.purpose)

onMounted(() => void refreshCaptcha())

function updateCode(value: string): void {
  emit('update:code', value)
}

async function handleSend(): Promise<void> {
  await sendCode(props.phone, (code) => emit('update:code', code))
}
</script>

<template>
  <el-form-item label="图形验证码">
    <div class="sms-field__row">
      <el-input v-model="captchaAnswer" maxlength="5" placeholder="不区分大小写" />
      <img
        v-if="captcha"
        class="sms-field__image"
        :src="captcha.image"
        alt="图形验证码"
        title="点击刷新"
        @click="refreshCaptcha"
      />
      <el-button v-else :loading="captchaLoading" @click="refreshCaptcha">获取</el-button>
    </div>
  </el-form-item>

  <el-form-item label="短信验证码" prop="code">
    <div class="sms-field__row">
      <el-input :model-value="code" maxlength="6" placeholder="6 位验证码" @update:model-value="updateCode" />
      <el-button :disabled="countdown > 0" :loading="sending" @click="handleSend">
        {{ countdown > 0 ? `${countdown} 秒后重发` : '发送验证码' }}
      </el-button>
    </div>
  </el-form-item>
</template>

<style scoped>
.sms-field__row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.sms-field__image {
  background: #edf2f7;
  border: 1px solid var(--lib-border);
  border-radius: 6px;
  cursor: pointer;
  height: 32px;
  width: 104px;
}
</style>
