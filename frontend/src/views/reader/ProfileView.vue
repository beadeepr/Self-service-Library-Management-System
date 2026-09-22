<script setup lang="ts">
/**
 * 个人中心：资料、实名认证、账号安全、信用与押金。
 *
 * 两处行为差异经实测确认，不要随意改动：
 * - 改密码后旧 access 立即失效（令牌里带密码哈希），所以必须主动登出并重新登录；
 * - 换手机号后令牌仍然有效，保持会话即可，不必重新登录。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { errorMessage } from '@/api/client'
import {
  changePassword,
  changePhone,
  listCreditEntries,
  listDepositEntries,
  updateMe,
  verifyIdentity,
  type CreditEntry,
  type DepositEntry,
} from '@/api/readers'
import { recordConsent } from '@/api/content'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import { isPhone, passwordProblem } from '@/utils/validators'
import { formatDateTime, formatMoney } from '@/utils/format'
import SmsCodeField from '@/components/SmsCodeField.vue'

/** 告知书版本号，与后端同意记录一起留痕。 */
const POLICY_VERSION = 'v1.0'

const router = useRouter()
const auth = useAuthStore()
const reader = useReaderStore()

const activeTab = ref('profile')
const profile = computed(() => reader.profile)
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    await reader.load(true)
  } catch (error) {
    ElMessage.error(errorMessage(error, '个人资料加载失败'))
  } finally {
    loading.value = false
  }
})

const creditLevelText = computed(() => {
  const level = profile.value?.credit_level
  if (level === 'untrusted') return '失信'
  if (level === 'restricted') return '受限'
  return '正常'
})

const creditLevelType = computed(() => {
  const level = profile.value?.credit_level
  if (level === 'untrusted') return 'danger' as const
  if (level === 'restricted') return 'warning' as const
  return 'success' as const
})

/* ---------------- 资料编辑 ---------------- */

const profileForm = reactive({ first_name: '', avatar: '', contact: '' })
const savingProfile = ref(false)

watch(
  profile,
  (value) => {
    if (!value) return
    profileForm.first_name = value.first_name
    profileForm.avatar = value.avatar
    profileForm.contact = value.contact
  },
  { immediate: true },
)

async function saveProfile(): Promise<void> {
  savingProfile.value = true
  try {
    // 手机号、角色、信用、押金在后端是只读字段，这里只提交可改的三项。
    // 清空用空字符串而不是 null：avatar/contact 是 blank=True 的非空字段，
    // 传 null 会被后端以「该字段不能为 null。」拒绝。
    const updated = await updateMe({
      first_name: profileForm.first_name,
      avatar: profileForm.avatar.trim(),
      contact: profileForm.contact.trim(),
    })
    reader.set(updated)
    ElMessage.success('资料已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    savingProfile.value = false
  }
}

/* ---------------- 实名认证 ---------------- */

const identityForm = reactive({ identity: '', agreed: false })
const verifying = ref(false)

async function submitIdentity(): Promise<void> {
  if (!identityForm.agreed) {
    ElMessage.warning('请先阅读并同意实名认证告知')
    return
  }
  if (!/^\d{17}[0-9Xx]$/.test(identityForm.identity)) {
    ElMessage.warning('请输入 18 位身份证号')
    return
  }
  verifying.value = true
  try {
    // 后端要求先有 purpose='identity' 的同意记录，否则核验会被直接拒绝。
    await recordConsent({ purpose: 'identity', granted: true, policy_version: POLICY_VERSION })
    await verifyIdentity(identityForm.identity)
    await reader.load(true)
    identityForm.identity = ''
    identityForm.agreed = false
    ElMessage.success('实名认证完成（模拟核验，未接入公安或第三方渠道）')
  } catch (error) {
    ElMessage.error(errorMessage(error, '实名认证失败'))
  } finally {
    verifying.value = false
  }
}

/* ---------------- 修改密码 ---------------- */

const passwordForm = reactive({ old_password: '', new_password: '', confirm: '' })
const changingPassword = ref(false)

async function submitPassword(): Promise<void> {
  const problem = passwordProblem(passwordForm.new_password)
  if (problem) {
    ElMessage.warning(problem)
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  changingPassword.value = true
  try {
    await changePassword(passwordForm.old_password, passwordForm.new_password)
    ElMessage.success('密码已修改，请重新登录')
    // 旧令牌随密码一起失效，这里主动清理，避免用户撞上一次 401。
    auth.forget()
    reader.reset()
    await router.push({ name: 'reader-login' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '修改密码失败'))
  } finally {
    changingPassword.value = false
  }
}

/* ---------------- 更换手机号 ---------------- */

const phoneForm = reactive({ phone: '', code: '' })
const changingPhone = ref(false)

async function submitPhone(): Promise<void> {
  if (!isPhone(phoneForm.phone)) {
    ElMessage.warning('请输入 11 位新手机号')
    return
  }
  if (phoneForm.phone === profile.value?.phone) {
    ElMessage.warning('新手机号与当前手机号相同')
    return
  }
  if (!phoneForm.code) {
    ElMessage.warning('请输入短信验证码')
    return
  }
  changingPhone.value = true
  try {
    const updated = await changePhone(phoneForm.phone, phoneForm.code)
    reader.set(updated)
    phoneForm.phone = ''
    phoneForm.code = ''
    ElMessage.success('手机号已更换')
  } catch (error) {
    ElMessage.error(errorMessage(error, '更换手机号失败'))
  } finally {
    changingPhone.value = false
  }
}

/* ---------------- 信用与押金流水 ---------------- */

const creditEntries = ref<CreditEntry[]>([])
const depositEntries = ref<DepositEntry[]>([])
const entriesLoading = ref(false)
const entriesLoaded = ref(false)

async function loadEntries(): Promise<void> {
  entriesLoading.value = true
  try {
    const [credit, deposit] = await Promise.all([listCreditEntries(), listDepositEntries()])
    creditEntries.value = credit.results
    depositEntries.value = deposit.results
    entriesLoaded.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error, '流水加载失败'))
  } finally {
    entriesLoading.value = false
  }
}

// 流水是低频查看的数据，切到该页签再加载，并记住已加载过。
watch(activeTab, (tab) => {
  if (tab === 'finance' && !entriesLoaded.value) void loadEntries()
})
</script>

<template>
  <div v-loading="loading" class="lib-stack">
    <el-card shadow="never">
      <div class="summary">
        <div>
          <h2 class="summary__name">{{ reader.displayName }}</h2>
          <p class="lib-text-muted">{{ profile?.phone ?? '—' }}</p>
        </div>
        <div class="summary__tags">
          <el-tag v-if="auth.isAdmin" type="danger" effect="plain">管理员</el-tag>
          <el-tag v-else-if="auth.isOperator" type="warning" effect="plain">运维</el-tag>
          <el-tag v-else effect="plain">读者</el-tag>
          <el-tag :type="profile?.verified ? 'success' : 'info'" effect="plain">
            {{ profile?.verified ? '已实名' : '未实名' }}
          </el-tag>
          <el-tag v-if="profile?.frozen" type="danger" effect="plain">已冻结</el-tag>
        </div>
      </div>

      <el-descriptions :column="3" border size="small" class="summary__stats">
        <el-descriptions-item label="信用分">
          {{ profile?.credit ?? '—' }}
          <el-tag :type="creditLevelType" size="small" effect="plain">{{ creditLevelText }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="押金余额">{{ formatMoney(profile?.deposit) }}</el-descriptions-item>
        <el-descriptions-item label="账号状态">{{ profile?.is_active ? '正常' : '已停用' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="我的资料" name="profile">
          <el-form :model="profileForm" label-width="90px" class="narrow-form" @submit.prevent>
            <el-form-item label="昵称">
              <el-input v-model="profileForm.first_name" maxlength="150" placeholder="用于借阅记录显示" />
            </el-form-item>
            <el-form-item label="联系方式">
              <el-input v-model="profileForm.contact" maxlength="150" placeholder="邮箱或备用联系方式" />
            </el-form-item>
            <el-form-item label="头像地址">
              <el-input v-model="profileForm.avatar" placeholder="图片 URL" />
            </el-form-item>
            <el-form-item label="手机号">
              <el-input :model-value="profile?.phone ?? ''" disabled />
              <span class="lib-text-muted">手机号需在「账号安全」中通过短信验证码更换</span>
            </el-form-item>
            <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="实名认证" name="identity">
          <el-alert
            v-if="profile?.verified"
            type="success"
            :closable="false"
            title="已完成实名认证"
            description="实名后借阅上限与借期按规则放宽。演示环境只做格式与唯一性模拟核验，不代表已完成公安或第三方核验。"
          />

          <el-form v-else :model="identityForm" label-width="90px" class="narrow-form" @submit.prevent>
            <el-alert
              type="info"
              :closable="false"
              class="identity-notice"
              title="实名认证告知"
              description="提交的证件号仅用于计算并保存不可逆摘要，不保存明文，仅用于唯一性校验。勾选同意后方可提交。"
            />
            <el-form-item label="身份证号">
              <el-input v-model="identityForm.identity" maxlength="18" placeholder="18 位身份证号" />
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="identityForm.agreed">我已阅读并同意上述实名认证告知</el-checkbox>
            </el-form-item>
            <el-button type="primary" :loading="verifying" @click="submitIdentity">提交认证</el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="账号安全" name="security">
          <div class="security">
            <section class="security__block">
              <h3 class="security__title">修改密码</h3>
              <p class="lib-text-muted">修改成功后当前登录会失效，需要用新密码重新登录。</p>
              <el-form :model="passwordForm" label-width="90px" class="narrow-form" @submit.prevent>
                <el-form-item label="原密码">
                  <el-input v-model="passwordForm.old_password" type="password" show-password />
                </el-form-item>
                <el-form-item label="新密码">
                  <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="至少 8 位，不能全为数字" />
                </el-form-item>
                <el-form-item label="确认新密码">
                  <el-input v-model="passwordForm.confirm" type="password" show-password />
                </el-form-item>
                <el-button type="primary" :loading="changingPassword" @click="submitPassword">修改密码</el-button>
              </el-form>
            </section>

            <el-divider />

            <section class="security__block">
              <h3 class="security__title">更换手机号</h3>
              <p class="lib-text-muted">验证码会发送到新手机号，验证通过后当前会话继续有效。</p>
              <el-form :model="phoneForm" label-width="90px" class="narrow-form" @submit.prevent>
                <el-form-item label="新手机号">
                  <el-input v-model="phoneForm.phone" maxlength="11" placeholder="11 位手机号" />
                </el-form-item>
                <SmsCodeField v-model:code="phoneForm.code" :phone="phoneForm.phone" purpose="phone" />
                <el-button type="primary" :loading="changingPhone" @click="submitPhone">更换手机号</el-button>
              </el-form>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane label="信用与押金" name="finance">
          <div v-loading="entriesLoading">
            <h3 class="security__title">信用流水</h3>
            <el-empty v-if="!creditEntries.length" description="暂无信用变动记录" :image-size="70" />
            <el-table v-else :data="creditEntries" size="small">
              <el-table-column prop="created_at" label="时间" width="180">
                <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column prop="delta" label="变动" width="90" />
              <el-table-column prop="balance" label="余额" width="90" />
              <el-table-column prop="reason" label="原因" min-width="200" />
            </el-table>

            <h3 class="security__title finance-title">押金流水</h3>
            <el-empty v-if="!depositEntries.length" description="暂无押金变动记录" :image-size="70" />
            <el-table v-else :data="depositEntries" size="small">
              <el-table-column prop="created_at" label="时间" width="180">
                <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="变动" width="110">
                <template #default="{ row }">{{ formatMoney(row.delta) }}</template>
              </el-table-column>
              <el-table-column label="余额" width="110">
                <template #default="{ row }">{{ formatMoney(row.balance) }}</template>
              </el-table-column>
              <el-table-column prop="reason" label="原因" min-width="200" />
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.summary {
  align-items: flex-start;
  display: flex;
  justify-content: space-between;
}

.summary__name {
  font-size: 18px;
  margin: 0 0 4px;
}

.summary__tags {
  display: flex;
  gap: 6px;
}

.summary__stats {
  margin-top: 16px;
}

.narrow-form {
  max-width: 460px;
}

.identity-notice {
  margin-bottom: 16px;
}

.security__title {
  font-size: 15px;
  margin: 0 0 4px;
}

.security__block :deep(.el-form-item:last-of-type) {
  margin-bottom: 16px;
}

.finance-title {
  margin-top: 24px;
}
</style>
