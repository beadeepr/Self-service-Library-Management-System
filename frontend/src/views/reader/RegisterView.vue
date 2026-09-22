<script setup lang="ts">
/**
 * 注册页，对应 FR-01。
 *
 * 顺序由后端决定，不能颠倒：先过图形验证码才发注册短信码，再用短信码 + 密码提交。
 * 注册只产生 reader 角色（后端强制）。注册成功后自动登录，省去再填一次手机号密码；
 * 若自动登录失败，退回登录页让用户手工登录。
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { register } from '@/api/auth'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { PHONE_PATTERN, passwordProblem } from '@/utils/validators'
import AuthCard from '@/components/AuthCard.vue'
import SmsCodeField from '@/components/SmsCodeField.vue'

const router = useRouter()
const auth = useAuthStore()
const reader = useReaderStore()

const formRef = ref<FormInstance>()
const form = reactive({ phone: '', code: '', first_name: '', password: '', confirm: '' })
const submitting = ref(false)

const rules: FormRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: PHONE_PATTERN, message: '请输入 11 位手机号', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入短信验证码', trigger: 'blur' }],
  password: [
    { required: true, message: '请设置密码', trigger: 'blur' },
    {
      // 只拦明显不合格的输入，常见弱口令与相似度由后端判定并回显。
      validator: (_rule, value: string, callback) => callback(passwordProblem(value) ?? undefined),
      trigger: 'blur',
    },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) =>
        callback(value === form.password ? undefined : new Error('两次输入的密码不一致')),
      trigger: 'blur',
    },
  ],
}

async function submit(): Promise<void> {
  const element = formRef.value
  if (!element) return
  if (!(await element.validate().catch(() => false))) return

  submitting.value = true
  try {
    await register({
      phone: form.phone,
      code: form.code,
      password: form.password,
      first_name: form.first_name || undefined,
    })
    reader.reset()
    try {
      await auth.login(form.phone, form.password)
      ElMessage.success('注册成功，已自动登录')
      await router.replace(auth.homePath())
    } catch {
      ElMessage.success('注册成功，请使用新账号登录')
      await router.replace({ name: 'reader-login' })
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, '注册失败'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthCard title="注册" subtitle="注册后可借阅、预约与查询个人借阅记录">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
      <el-form-item label="手机号" prop="phone">
        <el-input v-model="form.phone" maxlength="11" placeholder="11 位手机号" />
      </el-form-item>

      <SmsCodeField v-model:code="form.code" :phone="form.phone" purpose="register" />

      <el-form-item label="昵称" prop="first_name">
        <el-input v-model="form.first_name" maxlength="150" placeholder="选填，便于在借阅记录中显示" />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input v-model="form.password" type="password" show-password placeholder="至少 8 位，不能全为数字" />
      </el-form-item>

      <el-form-item label="确认密码" prop="confirm">
        <el-input v-model="form.confirm" type="password" show-password placeholder="再次输入密码" @keyup.enter="submit" />
      </el-form-item>

      <el-button class="auth-submit" type="primary" :loading="submitting" @click="submit">注册并登录</el-button>
    </el-form>

    <p class="auth-switch">
      已有账号？
      <RouterLink class="auth-switch__link" :to="{ name: 'reader-login' }">返回登录</RouterLink>
    </p>
  </AuthCard>
</template>

<style scoped>
.auth-submit {
  width: 100%;
}

.auth-switch {
  margin: 18px 0 0;
  text-align: center;
}

.auth-switch__link {
  color: var(--lib-brand);
}
</style>
