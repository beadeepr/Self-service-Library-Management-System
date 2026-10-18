<script setup lang="ts">
/**
 * 自助终端首页：读者签到 + 功能菜单。
 *
 * 终端是共用设备，采用「读者刷卡后以读者本人身份操作」的模型：
 * 签到即用该读者账号登录，后续借还都由后端按本人身份校验，
 * 不使用终端服务账号代借（那会把读者资格与信用校验绕过去）。
 * 演示环境用手机号 + 密码/短信码代替刷卡，真机应接读卡器。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { errorMessage } from '@/api/client'
import { fetchRules, listLoans, type LoanRules } from '@/api/circulation'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { useOfflineQueue } from '@/composables/useOfflineQueue'
import { PHONE_PATTERN } from '@/utils/validators'
import { formatDateTime } from '@/utils/format'
import SmsCodeField from '@/components/SmsCodeField.vue'

type Mode = 'password' | 'sms'

const router = useRouter()
const auth = useAuthStore()
const reader = useReaderStore()
const {
  items: offlineItems,
  syncing,
  clearing,
  refresh: refreshOffline,
  sync: syncOffline,
  clear: clearOffline,
} = useOfflineQueue()

const mode = ref<Mode>('password')
const signingIn = ref(false)
const passwordForm = reactive({ phone: '', password: '' })
const smsForm = reactive({ phone: '', code: '' })

const rules = ref<LoanRules | null>(null)
const activeLoanCount = ref(0)
const contextLoading = ref(false)

/** 签到后展示「已借 N 册 / 上限 M 册」，让读者进功能前就知道还能不能借。 */
const quotaText = computed(() => {
  if (!rules.value) return ''
  const limit = reader.isVerified ? rules.value.verified_loan_limit : rules.value.loan_limit
  return `已借 ${activeLoanCount.value} 册 / 上限 ${limit} 册`
})

async function refreshContext(): Promise<void> {
  contextLoading.value = true
  try {
    const [ruleData, loanPage] = await Promise.all([fetchRules(), listLoans({ 'returned_at__isnull': true })])
    rules.value = ruleData
    activeLoanCount.value = loanPage.count
  } catch (error) {
    ElMessage.error(errorMessage(error, '借阅信息加载失败'))
  } finally {
    contextLoading.value = false
  }
}

onMounted(() => {
  void refreshOffline()
  if (auth.isAuthenticated) {
    void reader.load(true).catch(() => undefined)
    void refreshContext()
  }
})

function validatePhone(phone: string): boolean {
  if (!PHONE_PATTERN.test(phone)) {
    ElMessage.warning('请输入 11 位手机号')
    return false
  }
  return true
}

async function signInWithPassword(): Promise<void> {
  if (!validatePhone(passwordForm.phone) || !passwordForm.password) {
    if (!passwordForm.password) ElMessage.warning('请输入密码')
    return
  }
  signingIn.value = true
  try {
    await auth.login(passwordForm.phone, passwordForm.password)
    reader.reset()
    await reader.load(true)
    await refreshContext()
    passwordForm.password = ''
    ElMessage.success(`欢迎，${reader.displayName}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '签到失败'))
  } finally {
    signingIn.value = false
  }
}

async function signInWithSms(): Promise<void> {
  if (!validatePhone(smsForm.phone) || !smsForm.code) {
    if (!smsForm.code) ElMessage.warning('请输入短信验证码')
    return
  }
  signingIn.value = true
  try {
    await auth.loginBySms(smsForm.phone, smsForm.code)
    reader.reset()
    await reader.load(true)
    await refreshContext()
    smsForm.code = ''
    ElMessage.success(`欢迎，${reader.displayName}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '签到失败'))
  } finally {
    signingIn.value = false
  }
}

async function finish(): Promise<void> {
  await auth.logout()
  reader.reset()
  rules.value = null
  activeLoanCount.value = 0
  passwordForm.phone = ''
  smsForm.phone = ''
  ElMessage.success('已结束使用')
}
</script>

<template>
  <div>
    <!-- 未签到：刷卡（演示为账号登录） -->
    <el-card v-if="!auth.isAuthenticated" shadow="never" class="signin">
      <h2 class="signin__title">请刷读者证</h2>
      <p class="kiosk-hint">演示环境可用手机号 + 密码或短信验证码代替刷卡</p>

      <el-radio-group v-model="mode" size="large" class="signin__mode">
        <el-radio-button value="password">密码</el-radio-button>
        <el-radio-button value="sms">短信验证码</el-radio-button>
      </el-radio-group>

      <div v-if="mode === 'password'" class="signin__form">
        <el-input v-model="passwordForm.phone" size="large" maxlength="11" placeholder="手机号" />
        <el-input
          v-model="passwordForm.password"
          size="large"
          type="password"
          show-password
          placeholder="密码"
          @keyup.enter="signInWithPassword"
        />
        <button class="kiosk-btn kiosk-btn--block" type="button" :disabled="signingIn" @click="signInWithPassword">
          {{ signingIn ? '签到中…' : '签到' }}
        </button>
      </div>

      <div v-else class="signin__form">
        <el-input v-model="smsForm.phone" size="large" maxlength="11" placeholder="手机号" />
        <SmsCodeField v-model:code="smsForm.code" :phone="smsForm.phone" purpose="login" />
        <button class="kiosk-btn kiosk-btn--block" type="button" :disabled="signingIn" @click="signInWithSms">
          {{ signingIn ? '签到中…' : '签到' }}
        </button>
      </div>
    </el-card>

    <!-- 已签到：功能菜单 -->
    <div v-else v-loading="contextLoading" class="menu">
      <el-card shadow="never" class="menu__welcome">
        <div class="menu__who">
          <span class="menu__name">{{ reader.displayName }}</span>
          <el-tag v-if="reader.isVerified" type="success" effect="plain">已实名</el-tag>
          <el-tag v-if="reader.creditLevel !== 'normal'" type="warning" effect="plain">
            {{ reader.creditLevel === 'untrusted' ? '失信' : '信用受限' }}
          </el-tag>
        </div>
        <p class="kiosk-hint">{{ quotaText }}</p>
      </el-card>

      <div class="menu__grid">
        <button class="menu__item" type="button" @click="router.push({ name: 'kiosk-borrow' })">
          <span class="menu__icon">借</span>
          <span class="menu__label">借书</span>
          <span class="kiosk-hint">刷书上的标签完成借阅</span>
        </button>

        <button class="menu__item" type="button" @click="router.push({ name: 'kiosk-return' })">
          <span class="menu__icon">还</span>
          <span class="menu__label">还书</span>
          <span class="kiosk-hint">支持跨馆归还</span>
        </button>

        <button class="menu__item" type="button" @click="router.push({ name: 'kiosk-access' })">
          <span class="menu__icon">门</span>
          <span class="menu__label">门禁通行</span>
          <span class="kiosk-hint">进馆 / 出馆登记</span>
        </button>

        <button class="menu__item menu__item--quiet" type="button" @click="finish">
          <span class="menu__icon">退</span>
          <span class="menu__label">结束使用</span>
          <span class="kiosk-hint">清除本机登录状态</span>
        </button>
      </div>

      <!-- 离线补传：断网时存入本机的交易在这里查看与补传 -->
      <el-card v-if="offlineItems.length" shadow="never" class="offline">
        <template #header>
          <div class="offline__head">
            <span>本机离线队列</span>
            <el-tag type="warning" effect="plain">{{ offlineItems.length }} 笔待补传</el-tag>
          </div>
        </template>

        <ul class="offline__list">
          <li v-for="item in offlineItems" :key="item.event_id" class="offline__item">
            <span class="offline__kind">{{ item.kind === 'borrow' ? '借书' : '还书' }}</span>
            <span class="kiosk-hint">
              {{ item.kind === 'borrow' ? `副本 ${item.copy}` : `借阅 ${item.loan}` }} ·
              {{ formatDateTime(item.occurred_at) }}
            </span>
            <el-tag v-if="item.sync === 'conflict'" type="danger" size="small" effect="plain">冲突</el-tag>
            <span v-if="item.message" class="offline__reason">{{ item.message }}</span>
          </li>
        </ul>

        <div class="offline__actions">
          <button class="kiosk-btn" type="button" :disabled="syncing" @click="syncOffline">
            {{ syncing ? '补传中…' : '尝试补传' }}
          </button>
          <button class="kiosk-btn kiosk-btn--ghost" type="button" :disabled="clearing" @click="clearOffline">清空</button>
        </div>

        <p class="kiosk-hint">
          补传会由服务端重新校验库存与读者资格，冲突不会被覆盖。
          注意：后端补传接口仅管理员可用，以读者身份登录的终端补传会被拒绝 ——
          这里演示的是本机队列与幂等去重机制，真实离线借还还需终端侧的离线身份凭证。
        </p>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.signin {
  margin: 0 auto;
  max-width: 520px;
}

.signin__title {
  font-size: var(--kiosk-title);
  margin: 0 0 6px;
  text-align: center;
}

.signin__mode {
  display: flex;
  justify-content: center;
  margin: 20px 0;
}

.signin__form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.menu__welcome {
  margin-bottom: 20px;
}

.menu__who {
  align-items: center;
  display: flex;
  gap: 10px;
}

.menu__name {
  font-size: 26px;
  font-weight: 700;
}

.menu__grid {
  display: grid;
  gap: 20px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.menu__item {
  align-items: flex-start;
  background: var(--kiosk-surface);
  border: 2px solid var(--kiosk-border);
  border-radius: 14px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 190px;
  padding: 24px;
  text-align: left;
}

.menu__item:hover {
  border-color: var(--lib-brand);
}

.menu__item--quiet {
  border-style: dashed;
}

.menu__icon {
  align-items: center;
  background: var(--lib-brand-soft);
  border-radius: 10px;
  color: var(--lib-brand);
  display: flex;
  font-size: 28px;
  font-weight: 700;
  height: 56px;
  justify-content: center;
  width: 56px;
}

.menu__label {
  font-size: 26px;
  font-weight: 700;
}

.offline {
  border-left: 4px solid #e6a23c;
  margin-top: 20px;
}

.offline__head {
  align-items: center;
  display: flex;
  gap: 10px;
}

.offline__list {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
}

.offline__item {
  align-items: center;
  border-bottom: 1px solid var(--lib-border);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 0;
}

.offline__item:last-child {
  border-bottom: none;
}

.offline__kind {
  font-weight: 700;
}

.offline__reason {
  color: var(--viz-status-critical);
  font-size: 14px;
}

.offline__actions {
  display: flex;
  gap: 12px;
}
</style>
