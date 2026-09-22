<script setup lang="ts">
/**
 * 罚款与押金，对应 FR-24~FR-26。
 *
 * 罚款由后端维护任务按天累计（不足一天按一天，费率取借阅规则），
 * 缴款是两步：先按未付余额创建订单，再走模拟支付通道结算。
 *
 * 要如实说明的两点：
 * 1. 未缴清罚款与逾期未还都会阻止继续借阅（后端 eligible 的判断之一），
 *    所以缴清后仍需归还逾期图书才能恢复借阅资格。
 * 2. 支付为模拟通道，未接入真实供应商。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import { isSettled, listFines, createPayment, simulatePayment, unpaidAmount, type Fine } from '@/api/fines'
import { fetchLoan, type Loan } from '@/api/circulation'
import { listDepositEntries, type DepositEntry } from '@/api/readers'
import { useCatalog } from '@/composables/useCatalog'
import { formatDateTime, formatMoney } from '@/utils/format'

const router = useRouter()
const { bookOfLoanCopy, ensureLoaded } = useCatalog()

interface FineRow {
  fine: Fine
  /** 罚款只带 loan 外键，书名与应还日期要经借阅记录取 */
  loan: Loan | null
}

const rows = ref<FineRow[]>([])
const deposits = ref<DepositEntry[]>([])
const loading = ref(false)
const payingId = ref<number | null>(null)

/** 每笔罚款保留一个幂等键：创建订单失败重试时复用，成功后清除。 */
const paymentKeys = new Map<number, string>()

const unpaidRows = computed(() => rows.value.filter((row) => !isSettled(row.fine)))
const settledRows = computed(() => rows.value.filter((row) => isSettled(row.fine)))
const totalUnpaid = computed(() => unpaidRows.value.reduce((sum, row) => sum + unpaidAmount(row.fine), 0))

async function load(): Promise<void> {
  loading.value = true
  try {
    const [finePage, depositPage] = await Promise.all([listFines(), listDepositEntries()])
    // 罚款只带 loan 外键，需按编号逐条取回借阅记录，才能显示书名与应还日期。
    const loans = await Promise.all(finePage.results.map((fine) => fetchLoan(fine.loan).catch(() => null)))
    rows.value = finePage.results.map((fine, index) => ({ fine, loan: loans[index] }))
    deposits.value = depositPage.results
  } catch (error) {
    rows.value = []
    deposits.value = []
    ElMessage.error(errorMessage(error, '罚款信息加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void ensureLoaded().catch(() => undefined)
  void load()
})

function bookTitle(row: FineRow): string {
  if (row.loan) return bookOfLoanCopy(row.loan.copy)?.title ?? `副本 ${row.loan.copy}`
  return `借阅 ${row.fine.loan}`
}

async function pay(row: FineRow): Promise<void> {
  const unpaid = unpaidAmount(row.fine)
  if (unpaid <= 0) {
    ElMessage.warning('该罚款已缴清')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认缴纳 ${formatMoney(unpaid)}？支付为模拟通道，不会产生真实扣款。`,
      '缴纳罚款',
      { type: 'info' },
    )
  } catch {
    return
  }

  payingId.value = row.fine.id
  const key = paymentKeys.get(row.fine.id) ?? newIdempotencyKey()
  paymentKeys.set(row.fine.id, key)
  try {
    const order = await createPayment(row.fine.id, key)
    paymentKeys.delete(row.fine.id)
    const settled = await simulatePayment(order.id)
    ElMessage.success(`已缴纳 ${formatMoney(order.amount)}，订单 ${String(order.reference).slice(0, 8)}，状态 ${settled.status === 'paid' ? '已支付' : settled.status}`)
    await load()
  } catch (error) {
    // 失败保留幂等键，重试不会重复下单。
    ElMessage.error(errorMessage(error, '缴纳失败'))
  } finally {
    payingId.value = null
  }
}
</script>

<template>
  <div v-loading="loading" class="lib-stack">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>未缴罚款</span>
          <el-tag v-if="totalUnpaid > 0" type="danger" effect="plain">合计 {{ formatMoney(totalUnpaid) }}</el-tag>
        </div>
      </template>

      <el-alert
        v-if="totalUnpaid > 0"
        type="warning"
        :closable="false"
        class="notice"
        title="有未缴清罚款"
        description="未缴清罚款会阻止继续借阅；若同时有逾期未还的图书，归还后借阅资格才会恢复。"
      />

      <el-empty v-if="!unpaidRows.length" description="没有待缴罚款" :image-size="70" />

      <el-table v-else :data="unpaidRows" size="small">
        <el-table-column label="图书" min-width="200">
          <template #default="{ row }">
            <div class="cell-title">{{ bookTitle(row) }}</div>
            <div class="lib-text-muted cell-sub">
              应还 {{ row.loan ? formatDateTime(row.loan.due_at) : '—' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="计费天数" width="100">
          <template #default="{ row }">{{ row.fine.assessed_days }} 天</template>
        </el-table-column>
        <el-table-column label="应缴" width="110">
          <template #default="{ row }">{{ formatMoney(row.fine.amount) }}</template>
        </el-table-column>
        <el-table-column label="未缴" width="110">
          <template #default="{ row }">
            <span class="cell-unpaid">{{ formatMoney(unpaidAmount(row.fine)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" :loading="payingId === row.fine.id" @click="pay(row)">
              缴纳
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>已缴记录</template>
      <el-empty v-if="!settledRows.length" description="暂无已缴记录" :image-size="70" />
      <el-table v-else :data="settledRows" size="small">
        <el-table-column label="图书" min-width="200">
          <template #default="{ row }">{{ bookTitle(row) }}</template>
        </el-table-column>
        <el-table-column label="计费天数" width="100">
          <template #default="{ row }">{{ row.fine.assessed_days }} 天</template>
        </el-table-column>
        <el-table-column label="金额" width="110">
          <template #default="{ row }">{{ formatMoney(row.fine.amount) }}</template>
        </el-table-column>
        <el-table-column label="已缴" width="110">
          <template #default="{ row }">{{ formatMoney(row.fine.paid_amount) }}</template>
        </el-table-column>
        <el-table-column label="缴清时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.fine.updated_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>押金流水</template>
      <el-empty v-if="!deposits.length" description="暂无押金变动记录" :image-size="70" />
      <el-table v-else :data="deposits" size="small">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="变动" width="110">
          <template #default="{ row }">{{ formatMoney(row.delta) }}</template>
        </el-table-column>
        <el-table-column label="余额" width="110">
          <template #default="{ row }">{{ formatMoney(row.balance) }}</template>
        </el-table-column>
        <el-table-column label="原因" min-width="200" prop="reason" />
      </el-table>
    </el-card>

    <p class="lib-text-muted">
      逾期罚款按天累计，不足一天按一天。支付为模拟通道；
      <el-button text type="primary" size="small" @click="router.push({ name: 'reader-loans' })">查看我的借阅</el-button>
    </p>
  </div>
</template>

<style scoped>
.head {
  align-items: center;
  display: flex;
  gap: 8px;
}

.notice {
  margin-bottom: 14px;
}

.cell-title {
  font-weight: 600;
}

.cell-sub {
  font-size: 12px;
}

.cell-unpaid {
  color: #f56c6c;
  font-weight: 600;
}
</style>
