<script setup lang="ts">
/**
 * 登录页，对应 FR-01~FR-03。
 *
 * 两种方式：手机号 + 密码、手机号 + 短信验证码。
 * 取码的图形码校验与倒计时由 SmsCodeField 内部处理，这里只管提交与跳转。
 */
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { PHONE_PATTERN } from '@/utils/validators'
import AuthCard from '@/components/AuthCard.vue'
import SmsCodeField from '@/components/SmsCodeField.vue'

type Mode = 'password' | 'sms'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const reader = useReaderStore()

const mode = ref<Mode>('password')
const submitting = ref(false)

const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({ phone: '', password: '' })
const passwordRules: FormRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: PHONE_PATTERN, message: '请输入 11 位手机号', trigger: 'blur' },
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const smsFormRef = ref<FormInstance>()
const smsForm = reactive({ phone: '', code: '' })
const smsRules: FormRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: PHONE_PATTERN, message: '请输入 11 位手机号', trigger: 'blur' },
  ],
  code: [{ required: true, message: '请输入短信验证码', trigger: 'blur' }],
}

const demoAccounts = [
  { phone: '13800000001', label: '管理员' },
  { phone: '13800000002', label: '读者' },
  { phone: '13800000003', label: '运维' },
]
// seed_demo 的默认口令，仅用于课程演示环境。
const DEMO_PASSWORD = 'Library-Demo-2026!'

onMounted(() => {
  // client.ts 在刷新令牌被拒时整页跳回这里并带上 expired 标记。
  if (route.query.expired) ElMessage.warning('登录已过期，请重新登录')
})

/** 登录成功后统一落地：优先回到来处，否则按角色进各自首页。 */
async function finishLogin(): Promise<void> {
  reader.reset()
  const target = route.query.redirect
  // 只接受站内绝对路径，避免被构造成站外跳转。
  const redirect = typeof target === 'string' && target.startsWith('/') ? target : null
  ElMessage.success('登录成功')
  await router.replace(redirect ?? auth.homePath())
}

async function submitPassword(): Promise<void> {
  const form = passwordFormRef.value
  if (!form) return
  if (!(await form.validate().catch(() => false))) return
  submitting.value = true
  try {
    await auth.login(passwordForm.phone, passwordForm.password)
    await finishLogin()
  } catch (error) {
    // 连续 5 次密码错误后端会锁定 15 分钟，错误文案由后端给出。
    ElMessage.error(errorMessage(error, '登录失败'))
  } finally {
    submitting.value = false
  }
}

async function submitSms(): Promise<void> {
  const form = smsFormRef.value
  if (!form) return
  if (!(await form.validate().catch(() => false))) return
  submitting.value = true
  try {
    await auth.loginBySms(smsForm.phone, smsForm.code)
    await finishLogin()
  } catch (error) {
    ElMessage.error(errorMessage(error, '登录失败'))
  } finally {
    submitting.value = false
  }
}

function useDemoAccount(phone: string): void {
  mode.value = 'password'
  passwordForm.phone = phone
  passwordForm.password = DEMO_PASSWORD
}
</script>

<template>
  <AuthCard title="登录" subtitle="无人值守图书馆系统">
    <el-tabs v-model="mode">
      <el-tab-pane label="密码登录" name="password">
        <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-position="top" @submit.prevent>
          <el-form-item label="手机号" prop="phone">
            <el-input v-model="passwordForm.phone" maxlength="11" placeholder="11 位手机号" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="passwordForm.password" type="password" show-password placeholder="请输入密码" @keyup.enter="submitPassword" />
          </el-form-item>
          <el-button class="auth-submit" type="primary" :loading="submitting" @click="submitPassword">登录</el-button>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="短信验证码登录" name="sms">
        <el-form ref="smsFormRef" :model="smsForm" :rules="smsRules" label-position="top" @submit.prevent>
          <el-form-item label="手机号" prop="phone">
            <el-input v-model="smsForm.phone" maxlength="11" placeholder="11 位手机号" />
          </el-form-item>
          <SmsCodeField v-model:code="smsForm.code" :phone="smsForm.phone" purpose="login" />
          <el-button class="auth-submit" type="primary" :loading="submitting" @click="submitSms">登录</el-button>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <el-divider>演示账号</el-divider>
    <div class="demo-accounts">
      <el-button v-for="account in demoAccounts" :key="account.phone" size="small" @click="useDemoAccount(account.phone)">
        {{ account.label }} · {{ account.phone }}
      </el-button>
    </div>
    <p class="demo-hint">点击任一演示账号可填入手机号与演示口令。账号与口令来自后端 seed_demo 命令。</p>

    <p class="auth-switch">
      还没有账号？
      <RouterLink class="auth-switch__link" :to="{ name: 'reader-register' }">立即注册</RouterLink>
    </p>
  </AuthCard>
</template>

<style scoped>
.auth-submit {
  width: 100%;
}

.demo-accounts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.demo-hint {
  color: var(--lib-text-muted);
  font-size: 12px;
  margin: 10px 0 0;
  text-align: center;
}

.auth-switch {
  margin: 18px 0 0;
  text-align: center;
}

.auth-switch__link {
  color: var(--lib-brand);
}
</style>
