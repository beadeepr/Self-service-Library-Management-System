<script setup lang="ts">
/**
 * 门禁通行，对应 FR-27~FR-28 与 FR-31。
 *
 * 演示环境用「已签到读者身份」代替真实读卡器：后端 AccessSerializer 支持
 * method=qr/card/face，人脸方式还要求最新的生物识别同意记录。
 * 入馆会校验信用、冻结、人数上限与重复入馆；出馆不受欠费或信用限制。
 *
 * 在馆人数与空闲座位是公开接口，且空闲座位由人数估算得出，
 * 未连接座位传感器，页面如实标注为「估算」。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import { fetchBranchOccupancy, type BranchOccupancy } from '@/api/books'
import { ACCESS_METHOD_LABEL, accessBranch, askForHelp, listVisits, type AccessMethod } from '@/api/iot'
import { useCatalog } from '@/composables/useCatalog'
import { useReaderStore } from '@/stores/reader'
import { formatDateTime } from '@/utils/format'

const reader = useReaderStore()
const { branches, ensureLoaded, branchName } = useCatalog()

const branch = ref<number | null>(null)
const occupancy = ref<BranchOccupancy | null>(null)
const insideSince = ref<string | null>(null)
/** 读者当前在馆的网点，用于把默认网点切到他实际在馆的那个 */
const insideBranch = ref<number | null>(null)
const method = ref<AccessMethod>('qr')
const busy = ref(false)
const lastResult = ref<{ direction: 'enter' | 'exit'; occupancy: number; at: string } | null>(null)

/** 每笔通行一个幂等键，重试复用，避免重复登记进出馆。 */
const accessKeys = new Map<string, string>()

const branchOptions = computed(() => branches.value.filter((item) => item.active))
const isInside = computed(() => !!insideSince.value)

const methodOptions: { value: AccessMethod; label: string }[] = [
  { value: 'qr', label: ACCESS_METHOD_LABEL.qr },
  { value: 'card', label: ACCESS_METHOD_LABEL.card },
  { value: 'face', label: ACCESS_METHOD_LABEL.face },
]

async function loadOccupancy(): Promise<void> {
  if (!branch.value) return
  try {
    occupancy.value = await fetchBranchOccupancy(branch.value)
  } catch {
    occupancy.value = null
  }
}

/**
 * 从本人的进馆记录判断当前是否在馆：未出馆的那条 exited_at 为空。
 * 若读者正在某网点馆内，把默认网点切到该网点 —— 否则「出馆」会在别的网点上被后端拒绝，
 * 读者会看到「没有对应的在馆记录」而不知道是网点选错了。
 */
async function loadMyStatus(): Promise<void> {
  try {
    const page = await listVisits()
    const open = page.results.find((item) => item.exited_at === null)
    insideSince.value = open?.entered_at ?? null
    insideBranch.value = open?.branch ?? null
    if (open && branchOptions.value.some((item) => item.id === open.branch)) {
      branch.value = open.branch
    }
  } catch {
    insideSince.value = null
    insideBranch.value = null
  }
}

onMounted(async () => {
  try {
    await ensureLoaded()
  } catch {
    // 网点取不到时不阻塞页面，只是无法选择网点。
  }
  branch.value = branchOptions.value[0]?.id ?? null
  // 先定状态（可能纠正默认网点），再按最终网点取在馆人数，避免取到错网点的数字。
  await loadMyStatus()
  await loadOccupancy()
})

async function pass(direction: 'enter' | 'exit'): Promise<void> {
  if (!branch.value) {
    ElMessage.warning('请选择网点')
    return
  }
  busy.value = true
  const name = `${direction}:${branch.value}`
  const key = accessKeys.get(name) ?? newIdempotencyKey()
  accessKeys.set(name, key)
  try {
    const result = await accessBranch(branch.value, direction, method.value, key)
    accessKeys.delete(name)
    lastResult.value = { direction: result.direction, occupancy: result.occupancy, at: new Date().toISOString() }
    ElMessage.success(direction === 'enter' ? '进馆成功，欢迎' : '出馆成功，再见')
    await Promise.all([loadOccupancy(), loadMyStatus()])
  } catch (error) {
    // 失败保留键，重试不会重复登记。
    ElMessage.error(errorMessage(error, direction === 'enter' ? '进馆失败' : '出馆失败'))
  } finally {
    busy.value = false
  }
}

async function help(): Promise<void> {
  if (!branch.value) return
  try {
    const { value } = await ElMessageBox.prompt('请简述遇到的问题，工作人员会收到告警', '紧急求助', {
      inputType: 'textarea',
      inputValidator: (text) => (text && text.trim() ? true : '请填写求助内容'),
    })
    await askForHelp(branch.value, value.trim())
    ElMessage.success('求助已发送，工作人员会尽快处理')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorMessage(error, '求助发送失败'))
  }
}
</script>

<template>
  <div class="access">
    <el-card shadow="never" class="access__head">
      <div class="access__who">
        <span class="access__name">{{ reader.displayName }}</span>
        <el-tag v-if="isInside" type="success" effect="plain">在馆中</el-tag>
        <el-tag v-else type="info" effect="plain">未在馆</el-tag>
      </div>
      <p v-if="isInside" class="kiosk-hint">进馆时间 {{ formatDateTime(insideSince) }}</p>

      <div class="access__stats">
        <div class="stat">
          <span class="stat__value">{{ occupancy?.occupancy ?? '—' }}</span>
          <span class="kiosk-hint">当前在馆人数</span>
        </div>
        <div class="stat">
          <span class="stat__value">{{ occupancy?.capacity ?? '—' }}</span>
          <span class="kiosk-hint">容量上限</span>
        </div>
        <div class="stat">
          <span class="stat__value">{{ occupancy?.estimated_free_seats ?? '—' }}</span>
          <span class="kiosk-hint">空闲座位（估算）</span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="access__form">
        <label class="access__label">网点</label>
        <el-select v-model="branch" size="large" class="access__select" @change="loadOccupancy">
          <el-option v-for="item in branchOptions" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <p v-if="insideBranch && branch && insideBranch !== branch" class="access__warn">
          你当前在「{{ branchName(insideBranch) }}」馆内，出馆请选该网点，否则会被拒绝。
        </p>

        <label class="access__label">身份方式</label>
        <el-radio-group v-model="method" size="large">
          <el-radio-button v-for="item in methodOptions" :key="item.value" :value="item.value">
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
      </div>

      <div class="access__actions">
        <button class="kiosk-btn" type="button" :disabled="busy" @click="pass('enter')">
          {{ busy ? '处理中…' : '进馆' }}
        </button>
        <button class="kiosk-btn kiosk-btn--ghost" type="button" :disabled="busy" @click="pass('exit')">出馆</button>
      </div>

      <p class="kiosk-hint">
        入馆需信用与账号状态正常且未超过人数上限，重复进馆会被拒绝；出馆不受欠费或信用限制。
        <template v-if="method === 'face'">人脸方式还要求已有最新的生物识别同意记录。</template>
      </p>

      <el-divider />

      <button class="kiosk-btn kiosk-btn--ghost access__help" type="button" @click="help">
        一键求助
      </button>
      <p class="kiosk-hint">求助会立即生成一条告警，由工作人员在后台处理。</p>
    </el-card>

    <el-card v-if="lastResult" shadow="never" class="access__result">
      <h3 class="access__result-title">
        {{ lastResult.direction === 'enter' ? '进馆成功' : '出馆成功' }}
      </h3>
      <p class="kiosk-hint">
        {{ branchName(branch) }} · 当前在馆 {{ lastResult.occupancy }} 人 · {{ formatDateTime(lastResult.at) }}
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.access {
  margin: 0 auto;
  max-width: 720px;
}

.access__head {
  margin-bottom: 20px;
}

.access__who {
  align-items: center;
  display: flex;
  gap: 12px;
}

.access__name {
  font-size: 26px;
  font-weight: 700;
}

.access__stats {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(3, 1fr);
  margin-top: 18px;
}

.stat {
  background: var(--lib-brand-soft);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  padding: 16px;
  text-align: center;
}

.stat__value {
  color: var(--lib-brand);
  font-size: 34px;
  font-weight: 700;
}

.access__form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}

.access__label {
  font-size: var(--kiosk-text);
  font-weight: 600;
}

.access__select {
  max-width: 320px;
}

.access__warn {
  color: #8a5a00;
  margin: 0;
}

.access__actions {
  display: flex;
  gap: 16px;
  margin-bottom: 14px;
}

.access__help {
  width: 100%;
}

.access__result {
  border-left: 4px solid #67c23a;
  margin-top: 20px;
}

.access__result-title {
  color: #2e7d32;
  font-size: 24px;
  margin: 0 0 6px;
}
</style>
