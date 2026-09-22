<script setup lang="ts">
/**
 * 我的借阅，对应 FR-16~FR-20。
 *
 * 三种视图互不重叠：在借、逾期、已归还。
 * 逾期用后端的 due_at__lt 过滤而不是在当前页里筛，否则翻页后结果会漏。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import { fetchRules, listLoans, renewLoan, type Loan, type LoanRules } from '@/api/circulation'
import { useCatalog } from '@/composables/useCatalog'
import { useReaderStore } from '@/stores/reader'
import { formatDate, formatMoney } from '@/utils/format'
import LoanTable from '@/components/LoanTable.vue'

type Tab = 'active' | 'overdue' | 'history'

const router = useRouter()
const reader = useReaderStore()
const { ensureLoaded } = useCatalog()

const PAGE_SIZE = 20

const activeTab = ref<Tab>('active')
const page = ref(1)
const loans = ref<Loan[]>([])
const total = ref(0)
const loading = ref(false)
const rules = ref<LoanRules | null>(null)
const renewingId = ref<number | null>(null)

/**
 * 续借的幂等键按借阅编号留存：同一笔借阅重试复用同一个键，成功后清除。
 * 否则网络超时后用户再点一次，会变成第二次续借。
 */
const renewKeys = new Map<number, string>()

const query = computed(() => {
  if (activeTab.value === 'active') return { 'returned_at__isnull': true }
  if (activeTab.value === 'overdue') {
    return { 'returned_at__isnull': true, 'due_at__lt': new Date().toISOString() }
  }
  return { 'returned_at__isnull': false }
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listLoans({ ...query.value, page: page.value })
    loans.value = data.results
    total.value = data.count
  } catch (error) {
    loans.value = []
    total.value = 0
    ElMessage.error(errorMessage(error, '借阅记录加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  void ensureLoaded().catch(() => undefined)
  try {
    rules.value = await fetchRules()
  } catch {
    // 规则只用于提示，取不到不影响借阅记录展示。
  }
})

// 切页签要回到第 1 页，否则会停在上一个页签的页码上。
watch(activeTab, () => {
  page.value = 1
})
watch([activeTab, page], () => void load(), { immediate: true })

/** 实名后借期与上限按规则的实名档位执行。 */
const effectiveLimit = computed(() => {
  if (!rules.value) return null
  return reader.isVerified
    ? { days: rules.value.verified_loan_days, limit: rules.value.verified_loan_limit }
    : { days: rules.value.loan_days, limit: rules.value.loan_limit }
})

async function renew(loan: Loan): Promise<void> {
  renewingId.value = loan.id
  const key = renewKeys.get(loan.id) ?? newIdempotencyKey()
  renewKeys.set(loan.id, key)
  try {
    const result = await renewLoan(loan.id, key)
    renewKeys.delete(loan.id)
    ElMessage.success(`续借成功，应还日期顺延至 ${formatDate(result.due_at)}`)
    await load()
  } catch (error) {
    // 失败时保留幂等键，用户重试会复用，不会重复续借。
    ElMessage.error(errorMessage(error, '续借失败'))
  } finally {
    renewingId.value = null
  }
}

function changePage(next: number): void {
  page.value = next
}
</script>

<template>
  <div class="lib-stack">
    <el-card shadow="never">
      <template #header>借阅规则</template>
      <el-descriptions v-if="rules" :column="4" size="small">
        <el-descriptions-item label="借期">
          {{ effectiveLimit?.days }} 天
          <el-tag v-if="reader.isVerified" type="success" size="small" effect="plain">实名档位</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="可借上限">{{ effectiveLimit?.limit }} 册</el-descriptions-item>
        <el-descriptions-item label="续借次数">{{ rules.renewal_limit }} 次 / 册</el-descriptions-item>
        <el-descriptions-item label="逾期罚款">{{ formatMoney(rules.fine_per_day) }} / 天</el-descriptions-item>
        <el-descriptions-item label="预约保留">{{ rules.hold_days }} 天</el-descriptions-item>
        <el-descriptions-item label="最低信用分">{{ rules.minimum_credit }}</el-descriptions-item>
        <el-descriptions-item label="归还后处理">
          {{ rules.disinfection_required ? '需消毒上架' : '直接上架' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="在借中" name="active" />
        <el-tab-pane label="已逾期" name="overdue" />
        <el-tab-pane label="借阅历史" name="history" />
      </el-tabs>

      <LoanTable :loans="loans" :loading="loading">
        <template #columns>
          <el-table-column label="操作" width="110" align="right">
            <template #default="{ row }">
              <el-button
                v-if="!row.returned_at"
                text
                type="primary"
                size="small"
                :loading="renewingId === row.id"
                @click="renew(row)"
              >
                续借
              </el-button>
            </template>
          </el-table-column>
        </template>
      </LoanTable>

      <el-empty
        v-if="!loading && !loans.length && activeTab === 'active'"
        description="当前没有在借图书"
      >
        <el-button type="primary" @click="router.push({ name: 'kiosk-home' })">去自助终端借书</el-button>
      </el-empty>

      <el-pagination
        v-if="total > PAGE_SIZE"
        class="pager"
        layout="prev, pager, next, total"
        :total="total"
        :page-size="PAGE_SIZE"
        :current-page="page"
        @current-change="changePage"
      />
    </el-card>
  </div>
</template>

<style scoped>
.pager {
  justify-content: center;
  margin-top: 16px;
}
</style>
