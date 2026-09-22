<script setup lang="ts">
/**
 * 借还管理，仅管理员。
 *
 * 后端 LoanViewSet 继承 OwnedReadViewSet：非管理员只能看到自己的借阅，
 * 且催还（AdminOnly）与代读者借还（本人或管理员）都不对运维开放，
 * 因此这页对整个「运维」角色没有意义，路由与菜单都已限定为 admin。
 *
 * 这里是 FR-19「异常兜底」的落点：读者在自助机操作失败、图书状态异常、
 * 或需要线下处理时，由管理员在后台按副本直接代办借还。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorMessage, getAll, newIdempotencyKey } from '@/api/client'
import { fetchBook, fetchCopy, searchCopies, type Book, type Copy } from '@/api/books'
import { borrowCopy, listLoans, remindLoan, returnLoan, type Loan } from '@/api/circulation'
import type { UserProfile } from '@/api/auth'
import { useCatalog } from '@/composables/useCatalog'
import { dueDescription, formatDateTime } from '@/utils/format'
import LoanTable from '@/components/LoanTable.vue'

type StatusFilter = 'active' | 'overdue' | 'history' | ''

const PAGE_SIZE = 20
const { branches, ensureLoaded, branchName } = useCatalog()

const loans = ref<Loan[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const statusFilter = ref<StatusFilter>('active')
const copyFilter = ref('')
const readerFilter = ref<number | null>(null)

/**
 * 借阅记录只带 reader 外键，后端不展开读者、也不支持按手机号检索，
 * 为了把「读者 5」显示成可认的人、并能用手机号筛人，这里一次取全读者做本地检索。
 * 读者量很大时应改为后端展开 loan.reader 或提供手机号检索。
 */
const allReaders = ref<UserProfile[]>([])

const readerLabelById = computed(() => {
  const map = new Map<number, string>()
  for (const reader of allReaders.value) {
    map.set(reader.id, `${reader.phone}${reader.first_name ? ' · ' + reader.first_name : ''}`)
  }
  return map
})

function readerText(id: number): string {
  return readerLabelById.value.get(id) ?? `读者 ${id}`
}

const query = computed(() => {
  const base: Record<string, unknown> = {}
  if (statusFilter.value === 'active') base['returned_at__isnull'] = true
  if (statusFilter.value === 'history') base['returned_at__isnull'] = false
  if (statusFilter.value === 'overdue') {
    base['returned_at__isnull'] = true
    base['due_at__lt'] = new Date().toISOString()
  }
  if (copyFilter.value.trim()) base.copy = Number(copyFilter.value.trim())
  if (readerFilter.value) base.reader = readerFilter.value
  return base
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
    ElMessage.error(errorMessage(error, '借阅列表加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  void ensureLoaded().catch(() => undefined)
  try {
    allReaders.value = await getAll<UserProfile>('/readers/')
  } catch {
    allReaders.value = []
  }
  await load()
})

function submitSearch(): void {
  page.value = 1
  void load()
}

function resetFilters(): void {
  statusFilter.value = 'active'
  copyFilter.value = ''
  readerFilter.value = null
  submitSearch()
}

function changePage(next: number): void {
  page.value = next
  void load()
}

/* ---------------- 催还 ---------------- */

const remindingId = ref<number | null>(null)

async function remind(loan: Loan): Promise<void> {
  remindingId.value = loan.id
  try {
    await remindLoan(loan.id)
    ElMessage.success('已发送站内催还通知')
  } catch (error) {
    ElMessage.error(errorMessage(error, '催还失败'))
  } finally {
    remindingId.value = null
  }
}

/* ---------------- 归还（异常兜底） ---------------- */

const returnVisible = ref(false)
const returnTarget = ref<Loan | null>(null)
const returnForm = reactive({ branch: null as number | null, damaged: false })
const returnKey = ref('')
const submitting = ref(false)

/** 副本 → 书目的解析结果缓存，仅用于弹窗里的展示。 */
const bookCache = new Map<number, Book | undefined>()
const returnTargetBook = computed(() => (returnTarget.value ? bookCache.get(returnTarget.value.copy) : undefined))

async function openReturn(loan: Loan): Promise<void> {
  returnTarget.value = loan
  returnForm.damaged = false
  returnKey.value = newIdempotencyKey()
  try {
    const copy = await fetchCopy(loan.copy)
    returnForm.branch = copy.branch
    if (!bookCache.has(loan.copy)) bookCache.set(loan.copy, await fetchBook(copy.book))
  } catch (error) {
    ElMessage.error(errorMessage(error, '副本信息加载失败'))
    returnForm.branch = null
  }
  returnVisible.value = true
}

async function submitReturn(): Promise<void> {
  if (!returnTarget.value || !returnForm.branch) {
    ElMessage.warning('请选择归还网点')
    return
  }
  submitting.value = true
  try {
    const result = await returnLoan(returnTarget.value.id, returnForm.branch, returnForm.damaged, returnKey.value)
    returnKey.value = ''
    ElMessage.success(`已归还，副本状态：${result.copy_status}${Number(result.fine) > 0 ? `，产生罚款 ¥${result.fine}` : ''}`)
    returnVisible.value = false
    void ensureLoaded(true).catch(() => undefined)
    await load()
  } catch (error) {
    // 失败保留键，重试不会重复归还。
    ElMessage.error(errorMessage(error, '归还失败'))
  } finally {
    submitting.value = false
  }
}

/* ---------------- 代读者手工借书 ---------------- */

const borrowVisible = ref(false)
const borrowForm = reactive({ reader: null as number | null, copyInput: '' })
const borrowKey = ref('')
const resolvedCopy = ref<Copy | null>(null)
const resolvedBook = ref<Book | null>(null)
const resolving = ref(false)

function openBorrow(): void {
  borrowForm.reader = null
  borrowForm.copyInput = ''
  resolvedCopy.value = null
  resolvedBook.value = null
  borrowKey.value = newIdempotencyKey()
  borrowVisible.value = true
}

/** 与自助终端一致：纯数字按副本编号直取，其余按 RFID 查，以服务端结果为准。 */
async function resolveBorrowCopy(): Promise<void> {
  const value = borrowForm.copyInput.trim()
  if (!value) {
    ElMessage.warning('请输入或扫描图书标签')
    return
  }
  resolving.value = true
  try {
    const located = /^\d+$/.test(value)
      ? await fetchCopy(value).catch(() => null)
      : ((await searchCopies({ rfid: value })).results[0] ?? null)
    if (!located) {
      ElMessage.error('没有找到这个标签对应的图书')
      return
    }
    resolvedCopy.value = located
    resolvedBook.value = await fetchBook(located.book)
  } catch (error) {
    ElMessage.error(errorMessage(error, '图书识别失败'))
  } finally {
    resolving.value = false
  }
}

async function submitBorrow(): Promise<void> {
  if (!borrowForm.reader) {
    ElMessage.warning('请选择读者')
    return
  }
  if (!resolvedCopy.value) {
    ElMessage.warning('请先识别图书')
    return
  }
  submitting.value = true
  try {
    const result = await borrowCopy(resolvedCopy.value.id, borrowKey.value, borrowForm.reader)
    borrowKey.value = ''
    ElMessage.success(`代借成功，应还日期 ${formatDateTime(result.due_at)}`)
    borrowVisible.value = false
    void ensureLoaded(true).catch(() => undefined)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '代借失败'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="lib-stack">
    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="statusFilter" placeholder="全部记录" class="toolbar__status" @change="submitSearch">
          <el-option label="在借中" value="active" />
          <el-option label="已逾期" value="overdue" />
          <el-option label="已归还" value="history" />
          <el-option label="全部记录" value="" />
        </el-select>
        <!-- 本地检索：后端只能按用户名模糊搜，本地筛选项里带了手机号，反而更好用 -->
        <el-select v-model="readerFilter" class="toolbar__reader" clearable filterable placeholder="按读者筛选（可搜手机号）" @change="submitSearch">
          <el-option v-for="item in allReaders" :key="item.id" :label="readerLabelById.get(item.id)" :value="item.id" />
        </el-select>
        <el-input v-model="copyFilter" class="toolbar__copy" clearable placeholder="副本编号" @keyup.enter="submitSearch" />
        <el-button type="primary" @click="submitSearch">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="success" @click="openBorrow">代读者借书</el-button>
      </div>

      <LoanTable :loans="loans" :loading="loading">
        <template #columns>
          <el-table-column label="读者" width="170">
            <template #default="{ row }">{{ readerText(row.reader) }}</template>
          </el-table-column>
          <el-table-column label="逾期" width="110">
            <template #default="{ row }">
              <span v-if="!row.returned_at && dueDescription(row.due_at).overdue" class="cell-overdue">
                {{ dueDescription(row.due_at).text }}
              </span>
              <span v-else class="lib-text-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="right">
            <template #default="{ row }">
              <template v-if="!row.returned_at">
                <el-button text type="primary" size="small" :loading="remindingId === row.id" @click="remind(row)">
                  催还
                </el-button>
                <el-button text type="danger" size="small" @click="openReturn(row)">归还</el-button>
              </template>
            </template>
          </el-table-column>
        </template>
      </LoanTable>

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

    <!-- 代办归还 -->
    <el-dialog v-model="returnVisible" title="代办归还" width="520px">
      <el-descriptions v-if="returnTarget" :column="1" border size="small" class="target">
        <el-descriptions-item label="借阅编号">{{ returnTarget.id }}</el-descriptions-item>
        <el-descriptions-item label="副本">{{ returnTarget.copy }}</el-descriptions-item>
        <el-descriptions-item label="书目">{{ returnTargetBook?.title ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="应还时间">{{ formatDateTime(returnTarget.due_at) }}</el-descriptions-item>
      </el-descriptions>

      <el-form :model="returnForm" label-width="100px">
        <el-form-item label="归还网点" required>
          <el-select v-model="returnForm.branch" class="dialog-select" placeholder="选择网点">
            <el-option v-for="item in branches" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="图书损坏">
          <el-switch v-model="returnForm.damaged" active-text="损坏归还后始终待处理" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="returnVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitReturn">确认归还</el-button>
      </template>
    </el-dialog>

    <!-- 代读者借书 -->
    <el-dialog v-model="borrowVisible" title="代读者借书" width="560px">
      <el-alert
        type="info"
        :closable="false"
        class="dialog-alert"
        title="用于读者在自助机操作失败等异常兜底。资格、信用与库存仍由后端校验，不会绕过规则。"
      />

      <el-form :model="borrowForm" label-width="100px">
        <el-form-item label="读者" required>
          <el-select v-model="borrowForm.reader" class="dialog-select" filterable placeholder="输入手机号或昵称检索">
            <el-option v-for="item in allReaders" :key="item.id" :label="readerLabelById.get(item.id)" :value="item.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="图书" required>
          <div class="resolve-row">
            <el-input v-model="borrowForm.copyInput" placeholder="扫描或输入标签 / 副本编号" @keyup.enter="resolveBorrowCopy" />
            <el-button :loading="resolving" @click="resolveBorrowCopy">识别</el-button>
          </div>
        </el-form-item>
      </el-form>

      <el-descriptions v-if="resolvedCopy" :column="1" border size="small">
        <el-descriptions-item label="书目">{{ resolvedBook?.title ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="副本">{{ resolvedCopy.id }} · {{ resolvedCopy.shelf }} 架 · {{ branchName(resolvedCopy.branch) }}</el-descriptions-item>
        <el-descriptions-item label="当前状态">{{ resolvedCopy.status }}</el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button @click="borrowVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitBorrow">确认借出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.toolbar__status {
  width: 130px;
}

.toolbar__reader {
  width: 220px;
}

.toolbar__copy {
  width: 140px;
}

.cell-overdue {
  color: #f56c6c;
  font-weight: 600;
}

.pager {
  justify-content: center;
  margin-top: 16px;
}

.target {
  margin-bottom: 16px;
}

.dialog-select {
  width: 100%;
}

.dialog-alert {
  margin-bottom: 16px;
}

.resolve-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
</style>
