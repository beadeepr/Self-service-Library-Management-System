<script setup lang="ts">
/**
 * 自助借书，三步：识别副本 → 确认借阅 → 打印凭条。
 *
 * 两个不能含糊的点：
 * 1. 借书接口收的是 copy（物理副本 ID），不是书目 ID，所以必须先把标签解析成副本，
 *    再校验该副本是否真的可借 —— 校验走服务端查询，不用本地缓存的副本快照，
 *    否则别人刚借走的书在这台终端上仍显示可借。
 * 2. 幂等键在「识别到副本」时生成，之后重试复用同一个键，只有开始新一笔交易才换新键。
 *    否则网络超时后用户再点一次确认，会变成借两本。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError, errorMessage, newIdempotencyKey } from '@/api/client'
import { COPY_STATUS_LABEL, fetchBook, fetchCopy, searchCopies, type Book, type Copy } from '@/api/books'
import { borrowCopy, fetchRules, type BorrowResult, type LoanRules } from '@/api/circulation'
import { useCatalog } from '@/composables/useCatalog'
import { isNetworkFailure, useOfflineQueue } from '@/composables/useOfflineQueue'
import { useReaderStore } from '@/stores/reader'
import { formatDate, formatDateTime } from '@/utils/format'

type Step = 'scan' | 'confirm' | 'done'

const router = useRouter()
const reader = useReaderStore()
const { branchName, ensureLoaded } = useCatalog()
const { offerOnNetworkFailure } = useOfflineQueue()

const step = ref<Step>('scan')
const rfidInput = ref('')
const copy = ref<Copy | null>(null)
const book = ref<Book | null>(null)
const result = ref<BorrowResult | null>(null)
const rules = ref<LoanRules | null>(null)
const busy = ref(false)

/** 本笔交易的幂等键，识别到副本时生成，成功后清空。 */
const transactionKey = ref('')

onMounted(async () => {
  void ensureLoaded().catch(() => undefined)
  try {
    rules.value = await fetchRules()
  } catch {
    // 规则只用于展示借期，取不到不阻塞借书（应由服务端作最终裁定）。
  }
})

const loanDays = computed(() => {
  if (!rules.value) return null
  return reader.isVerified ? rules.value.verified_loan_days : rules.value.loan_days
})

/** 预计应还日期：仅作提示，最终以借出后服务端返回的 due_at 为准（节假日会顺延）。 */
const expectedDue = computed(() => {
  if (loanDays.value === null) return null
  const date = new Date()
  date.setDate(date.getDate() + loanDays.value)
  return date
})

function resetTransaction(): void {
  step.value = 'scan'
  rfidInput.value = ''
  copy.value = null
  book.value = null
  result.value = null
  transactionKey.value = ''
}

/**
 * 标签 → 副本。纯数字按副本编号直取，其余按 RFID 查；一律以服务端结果为准，
 * 不用本地缓存的副本快照，否则别人刚借走的书在这里仍会显示可借。
 */
async function resolveCopy(raw: string): Promise<void> {
  const value = raw.trim()
  if (!value) {
    ElMessage.warning('请扫描或输入图书标签')
    return
  }

  busy.value = true
  try {
    const located = /^\d+$/.test(value)
      ? await fetchCopy(value).catch(() => null)
      : ((await searchCopies({ rfid: value })).results[0] ?? null)

    if (!located) {
      ElMessage.error('没有找到这个标签对应的图书，请确认标签或联系管理员')
      return
    }
    if (located.status !== 'available') {
      ElMessage.error(`该图书当前状态为「${COPY_STATUS_LABEL[located.status]}」，暂不可借`)
      return
    }

    copy.value = located
    book.value = await fetchBook(located.book)
    transactionKey.value = newIdempotencyKey()
    step.value = 'confirm'
  } catch (error) {
    ElMessage.error(errorMessage(error, '图书识别失败'))
  } finally {
    busy.value = false
  }
}

/**
 * 演示用：从服务端取一本确实可借的副本，走与扫码完全相同的解析流程。
 * 真机由 RFID 读写器上报标签，这里只是替掉「读标签」这一步。
 */
async function simulateScan(): Promise<void> {
  busy.value = true
  try {
    const page = await searchCopies({ status: 'available' })
    const candidate = page.results[0]
    if (!candidate) {
      ElMessage.warning('当前没有可借副本')
      return
    }
    rfidInput.value = candidate.rfid
    busy.value = false
    await resolveCopy(candidate.rfid)
  } catch (error) {
    busy.value = false
    ElMessage.error(errorMessage(error, '取可借副本失败'))
  }
}

async function confirmBorrow(): Promise<void> {
  if (!copy.value) return
  busy.value = true
  try {
    result.value = await borrowCopy(copy.value.id, transactionKey.value)
    step.value = 'done'
    // 副本状态已变，刷新对照数据，避免下一笔还用旧快照判断。
    void ensureLoaded(true).catch(() => undefined)
  } catch (error) {
    if (error instanceof ApiError && error.isOutOfStock) {
      // 4001 是后端约定的「库存不可借」，通常是并发借出，退回重扫。
      ElMessage.error(error.message)
      resetTransaction()
    } else if (isNetworkFailure(error)) {
      // 断网时服务端可能已受理也可能没有，按 FR-34 存入本机队列待网络恢复后补传校验。
      await offerOnNetworkFailure({
        kind: 'borrow',
        reader: reader.profile?.id,
        copy: copy.value.id,
      })
      resetTransaction()
    } else {
      ElMessage.error(errorMessage(error, '借阅失败'))
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="borrow">
    <el-steps :active="step === 'scan' ? 0 : step === 'confirm' ? 1 : 2" finish-status="success" class="borrow__steps">
      <el-step title="识别图书" />
      <el-step title="确认借阅" />
      <el-step title="完成" />
    </el-steps>

    <!-- 第 1 步：识别 -->
    <el-card v-if="step === 'scan'" shadow="never">
      <h2 class="borrow__title">请把图书放在感应区</h2>
      <p class="kiosk-hint">也可以手工输入标签或副本编号</p>

      <div class="borrow__scan">
        <el-input
          v-model="rfidInput"
          size="large"
          placeholder="图书标签（RFID）或副本编号"
          @keyup.enter="resolveCopy(rfidInput)"
        />
        <button class="kiosk-btn" type="button" :disabled="busy" @click="resolveCopy(rfidInput)">识别</button>
      </div>

      <button class="kiosk-btn kiosk-btn--ghost borrow__demo" type="button" :disabled="busy" @click="simulateScan">
        演示：自动取一本可借图书
      </button>
    </el-card>

    <!-- 第 2 步：确认 -->
    <el-card v-else-if="step === 'confirm'" shadow="never">
      <h2 class="borrow__title">确认借阅</h2>

      <div class="borrow__book">
        <div class="borrow__cover">{{ book?.title.slice(0, 1) ?? '书' }}</div>
        <div>
          <p class="borrow__book-title">{{ book?.title ?? '未知书目' }}</p>
          <p class="kiosk-hint">{{ book?.author || '佚名' }}</p>
          <p class="kiosk-hint">
            架位 {{ copy?.shelf }} · {{ branchName(copy?.branch) }}
          </p>
          <p class="kiosk-hint">副本 {{ copy?.id }} / 标签 {{ copy?.rfid }}</p>
        </div>
      </div>

      <el-alert type="info" :closable="false" class="borrow__notice">
        <template #title>
          借期 {{ loanDays ?? '—' }} 天，预计应还 {{ expectedDue ? formatDate(expectedDue.toISOString()) : '—' }}
        </template>
        遇节假日的应还日期会顺延，最终以借出结果为准。
      </el-alert>

      <div class="borrow__actions">
        <button class="kiosk-btn kiosk-btn--ghost" type="button" :disabled="busy" @click="resetTransaction">返回重扫</button>
        <button class="kiosk-btn" type="button" :disabled="busy" @click="confirmBorrow">
          {{ busy ? '处理中…' : '确认借阅' }}
        </button>
      </div>
    </el-card>

    <!-- 第 3 步：完成 -->
    <el-card v-else shadow="never" class="borrow__done">
      <h2 class="borrow__done-title">借阅成功</h2>
      <p class="borrow__book-title">{{ book?.title }}</p>
      <p class="kiosk-hint">借阅编号 {{ result?.id }} · 副本 {{ result?.copy }}</p>

      <el-descriptions :column="1" border class="borrow__result">
        <el-descriptions-item label="应还日期">
          <span class="borrow__due">{{ formatDateTime(result?.due_at) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="借阅人">{{ reader.displayName }}</el-descriptions-item>
      </el-descriptions>

      <div class="borrow__actions">
        <button class="kiosk-btn" type="button" @click="resetTransaction">再借一本</button>
        <button class="kiosk-btn kiosk-btn--ghost" type="button" @click="router.push({ name: 'kiosk-home' })">
          返回菜单
        </button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.borrow {
  margin: 0 auto;
  max-width: 720px;
}

.borrow__steps {
  margin-bottom: 24px;
}

.borrow__title {
  font-size: var(--kiosk-title);
  margin: 0 0 6px;
}

.borrow__scan {
  display: flex;
  gap: 12px;
  margin: 18px 0;
}

.borrow__demo {
  width: 100%;
}

.borrow__book {
  display: flex;
  gap: 20px;
  margin: 18px 0;
}

.borrow__cover {
  align-items: center;
  background: var(--lib-brand-soft);
  border-radius: 12px;
  color: var(--lib-brand);
  display: flex;
  flex: none;
  font-size: 40px;
  font-weight: 700;
  height: 130px;
  justify-content: center;
  width: 96px;
}

.borrow__book-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
}

.borrow__notice {
  margin-bottom: 20px;
}

.borrow__actions {
  display: flex;
  gap: 16px;
}

.borrow__done {
  text-align: center;
}

.borrow__done-title {
  color: #2e7d32;
  font-size: var(--kiosk-title);
  margin: 0 0 8px;
}

.borrow__result {
  margin: 20px 0;
  text-align: left;
}

.borrow__due {
  font-size: 22px;
  font-weight: 700;
}
</style>
