<script setup lang="ts">
/**
 * 自助还书，三步：识别副本 → 确认归还 → 完成。
 *
 * 还书接口需要 loan（借阅编号）和一个归还网点，而读者手里只有书。
 * 所以流程是：标签 → 副本 → 查该副本当前未归还的借阅记录 → 再归还。
 * 支持跨馆归还，归还网点默认取副本所属网点，可改。
 *
 * 归还后副本默认进入待处理（需消毒上架），接口返回的 copy_status 与 fine 要如实展示，
 * 不能让读者以为立刻就能再次借出、或者以为一定不产生罚款。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import { COPY_STATUS_LABEL, fetchBook, fetchCopy, searchCopies, type Book, type Copy } from '@/api/books'
import { fetchRules, listLoans, returnLoan, type Loan, type LoanRules, type ReturnResult } from '@/api/circulation'
import { useCatalog } from '@/composables/useCatalog'
import { isNetworkFailure, useOfflineQueue } from '@/composables/useOfflineQueue'
import { useReaderStore } from '@/stores/reader'
import { dueDescription, formatDateTime, formatMoney } from '@/utils/format'

type Step = 'scan' | 'confirm' | 'done'

const router = useRouter()
const reader = useReaderStore()
const { branches, branchName, ensureLoaded } = useCatalog()
const { offerOnNetworkFailure } = useOfflineQueue()

const step = ref<Step>('scan')
const rfidInput = ref('')
const copy = ref<Copy | null>(null)
const book = ref<Book | null>(null)
const loan = ref<Loan | null>(null)
const result = ref<ReturnResult | null>(null)
const rules = ref<LoanRules | null>(null)
const returnBranch = ref<number | null>(null)
const damaged = ref(false)
const busy = ref(false)

/** 本笔交易的幂等键，识别到借阅记录时生成。 */
const transactionKey = ref('')

onMounted(async () => {
  try {
    await ensureLoaded()
  } catch {
    // 网点列表取不到时下面的下拉为空，仍可依靠默认网点提交。
  }
  try {
    rules.value = await fetchRules()
  } catch {
    // 罚款规则仅用于提示，最终金额以归还结果为准。
  }
})

const overdue = computed(() => (loan.value ? dueDescription(loan.value.due_at) : null))

function resetTransaction(): void {
  step.value = 'scan'
  rfidInput.value = ''
  copy.value = null
  book.value = null
  loan.value = null
  result.value = null
  returnBranch.value = null
  damaged.value = false
  transactionKey.value = ''
}

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
      ElMessage.error('没有找到这个标签对应的图书')
      return
    }

    const openLoans = await listLoans({ copy: located.id, 'returned_at__isnull': true })
    const active = openLoans.results[0]
    if (!active) {
      ElMessage.error('该图书当前没有在借记录，无需归还')
      return
    }

    copy.value = located
    book.value = await fetchBook(located.book)
    loan.value = active
    // 默认归还到副本所属网点，读者可就近跨馆归还。
    returnBranch.value = located.branch
    transactionKey.value = newIdempotencyKey()
    step.value = 'confirm'
  } catch (error) {
    ElMessage.error(errorMessage(error, '图书识别失败'))
  } finally {
    busy.value = false
  }
}

async function simulateScan(): Promise<void> {
  busy.value = true
  try {
    const page = await searchCopies({ status: 'loaned' })
    const candidate = page.results[0]
    if (!candidate) {
      ElMessage.warning('当前没有已借出的副本可以归还')
      return
    }
    rfidInput.value = candidate.rfid
    busy.value = false
    await resolveCopy(candidate.rfid)
  } catch (error) {
    busy.value = false
    ElMessage.error(errorMessage(error, '取在借副本失败'))
  }
}

async function confirmReturn(): Promise<void> {
  if (!loan.value || !returnBranch.value) {
    ElMessage.warning('请选择归还网点')
    return
  }
  busy.value = true
  try {
    result.value = await returnLoan(loan.value.id, returnBranch.value, damaged.value, transactionKey.value)
    step.value = 'done'
    void ensureLoaded(true).catch(() => undefined)
  } catch (error) {
    if (isNetworkFailure(error)) {
      // 断网时服务端可能已受理也可能没有，按 FR-34 存入本机队列待网络恢复后补传校验。
      await offerOnNetworkFailure({
        kind: 'return',
        loan: loan.value.id,
        branch: returnBranch.value,
      })
      resetTransaction()
    } else {
      ElMessage.error(errorMessage(error, '归还失败'))
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="return">
    <el-steps :active="step === 'scan' ? 0 : step === 'confirm' ? 1 : 2" finish-status="success" class="return__steps">
      <el-step title="识别图书" />
      <el-step title="确认归还" />
      <el-step title="完成" />
    </el-steps>

    <el-card v-if="step === 'scan'" shadow="never">
      <h2 class="return__title">请把图书放在感应区</h2>
      <p class="kiosk-hint">也可以手工输入标签或副本编号</p>

      <div class="return__scan">
        <el-input
          v-model="rfidInput"
          size="large"
          placeholder="图书标签（RFID）或副本编号"
          @keyup.enter="resolveCopy(rfidInput)"
        />
        <button class="kiosk-btn" type="button" :disabled="busy" @click="resolveCopy(rfidInput)">识别</button>
      </div>

      <button class="kiosk-btn kiosk-btn--ghost return__demo" type="button" :disabled="busy" @click="simulateScan">
        演示：自动取一本在借图书
      </button>
    </el-card>

    <el-card v-else-if="step === 'confirm'" shadow="never">
      <h2 class="return__title">确认归还</h2>

      <div class="return__book">
        <div class="return__cover">{{ book?.title.slice(0, 1) ?? '书' }}</div>
        <div>
          <p class="return__book-title">{{ book?.title ?? '未知书目' }}</p>
          <p class="kiosk-hint">{{ book?.author || '佚名' }}</p>
          <p class="kiosk-hint">架位 {{ copy?.shelf }} · 原属 {{ branchName(copy?.branch) }}</p>
          <p class="kiosk-hint">借出 {{ formatDateTime(loan?.borrowed_at) }} · 应还 {{ formatDateTime(loan?.due_at) }}</p>
        </div>
      </div>

      <el-alert
        :type="overdue?.overdue ? 'warning' : 'success'"
        :closable="false"
        class="return__notice"
      >
        <template #title>{{ overdue?.overdue ? overdue.text : '未逾期' }}</template>
        <template v-if="overdue?.overdue">
          逾期罚款 {{ formatMoney(rules?.fine_per_day) }} / 天，不足一天按一天，最终金额以归还结果为准。
        </template>
        <template v-else>在应还日期前归还，不产生罚款。</template>
      </el-alert>

      <div class="return__form">
        <label class="return__label">归还网点</label>
        <el-select v-model="returnBranch" size="large" placeholder="选择归还网点" class="return__select">
          <el-option v-for="item in branches" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-checkbox v-model="damaged" size="large">图书有损坏</el-checkbox>
      </div>

      <div class="return__actions">
        <button class="kiosk-btn kiosk-btn--ghost" type="button" :disabled="busy" @click="resetTransaction">返回重扫</button>
        <button class="kiosk-btn" type="button" :disabled="busy" @click="confirmReturn">
          {{ busy ? '处理中…' : '确认归还' }}
        </button>
      </div>
    </el-card>

    <el-card v-else shadow="never" class="return__done">
      <h2 class="return__done-title">归还成功</h2>
      <p class="return__book-title">{{ book?.title }}</p>
      <p class="kiosk-hint">借阅编号 {{ result?.id }}</p>

      <el-descriptions :column="1" border class="return__result">
        <el-descriptions-item label="产生罚款">
          <span :class="{ 'return__fine': Number(result?.fine) > 0 }">{{ formatMoney(result?.fine) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="图书状态">
          <el-tag type="warning" effect="plain">
            {{ COPY_STATUS_LABEL[result?.copy_status ?? 'processing'] }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="归还人">{{ reader.displayName }}</el-descriptions-item>
      </el-descriptions>

      <p class="kiosk-hint">
        归还的图书需经消毒上架后才可再次外借，请放入还书箱。
      </p>

      <div class="return__actions">
        <button class="kiosk-btn" type="button" @click="resetTransaction">再还一本</button>
        <button class="kiosk-btn kiosk-btn--ghost" type="button" @click="router.push({ name: 'kiosk-home' })">
          返回菜单
        </button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.return {
  margin: 0 auto;
  max-width: 720px;
}

.return__steps {
  margin-bottom: 24px;
}

.return__title {
  font-size: var(--kiosk-title);
  margin: 0 0 6px;
}

.return__scan {
  display: flex;
  gap: 12px;
  margin: 18px 0;
}

.return__demo {
  width: 100%;
}

.return__book {
  display: flex;
  gap: 20px;
  margin: 18px 0;
}

.return__cover {
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

.return__book-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
}

.return__notice {
  margin-bottom: 20px;
}

.return__form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 20px;
}

.return__label {
  font-size: var(--kiosk-text);
  font-weight: 600;
}

.return__select {
  max-width: 320px;
}

.return__actions {
  display: flex;
  gap: 16px;
}

.return__done {
  text-align: center;
}

.return__done-title {
  color: #2e7d32;
  font-size: var(--kiosk-title);
  margin: 0 0 8px;
}

.return__result {
  margin: 20px 0;
  text-align: left;
}

.return__fine {
  color: #f56c6c;
  font-size: 22px;
  font-weight: 700;
}
</style>
