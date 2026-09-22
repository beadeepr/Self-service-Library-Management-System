<script setup lang="ts">
/**
 * 图书与馆藏管理：书目 CRUD、入库、副本状态流转。
 *
 * 权限按后端分区，前端据此控制入口（真正的边界仍在后端）：
 * - 书目增删改、入库、副本下架报损 → 仅 admin
 * - 副本消毒、上架 → admin 与 operator
 * 因此运维账号进这页是「可消毒上架、其余只读」，不是整页禁用。
 *
 * 概念上书目与副本是两层：书目只有元数据，库存数量由副本统计；
 * 入库是「按数量生成副本并分配唯一 RFID」，不是改书目上的数字。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import {
  COPY_STATUS_LABEL,
  createBook,
  deleteBook,
  disinfectCopy,
  intakeCopies,
  searchBooks,
  searchCopies,
  setCopyStatus,
  shelveCopy,
  updateBook,
  type Book,
  type Copy,
  type CopyStatus,
} from '@/api/books'
import { useAuthStore } from '@/stores/auth'
import { useCatalog } from '@/composables/useCatalog'
import { formatDateTime, formatMoney } from '@/utils/format'

const auth = useAuthStore()
const { categories, branches, ensureLoaded, categoryName, branchName } = useCatalog()

const PAGE_SIZE = 20

const books = ref<Book[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const keyword = ref('')
const categoryFilter = ref<number | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await searchBooks({
      search: keyword.value.trim(),
      category: categoryFilter.value ?? '',
      page: page.value,
    })
    books.value = data.results
    total.value = data.count
  } catch (error) {
    books.value = []
    total.value = 0
    ElMessage.error(errorMessage(error, '书目加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await ensureLoaded()
  } catch {
    // 分类与网点取不到只影响下拉选项，不阻塞列表。
  }
  await load()
})

function submitSearch(): void {
  page.value = 1
  void load()
}

function changePage(next: number): void {
  page.value = next
  void load()
}

/* ---------------- 书目新增 / 编辑 ---------------- */

const formVisible = ref(false)
const editingId = ref<number | null>(null)
const submitting = ref(false)
const form = reactive({
  isbn: '',
  title: '',
  author: '',
  category: null as number | null,
  call_number: '',
  price: '0.00',
  publisher: '',
  cover: '',
  active: true,
})

const formTitle = computed(() => (editingId.value ? '编辑书目' : '新增书目'))

function openCreate(): void {
  editingId.value = null
  Object.assign(form, { isbn: '', title: '', author: '', category: null, call_number: '', price: '0.00', publisher: '', cover: '', active: true })
  formVisible.value = true
}

function openEdit(book: Book): void {
  editingId.value = book.id
  Object.assign(form, {
    isbn: book.isbn,
    title: book.title,
    author: book.author,
    category: book.category,
    call_number: book.call_number,
    price: book.price,
    publisher: book.publisher,
    cover: book.cover,
    active: book.active,
  })
  formVisible.value = true
}

async function submitForm(): Promise<void> {
  if (!form.isbn || !form.title || !form.author || !form.call_number) {
    ElMessage.warning('ISBN、书名、作者、索书号为必填')
    return
  }
  if (!form.category) {
    ElMessage.warning('请选择分类')
    return
  }
  submitting.value = true
  try {
    const payload = {
      isbn: form.isbn.trim(),
      title: form.title.trim(),
      author: form.author.trim(),
      category: form.category,
      call_number: form.call_number.trim(),
      price: form.price,
      publisher: form.publisher.trim(),
      cover: form.cover.trim(),
      active: form.active,
    }
    if (editingId.value) {
      await updateBook(editingId.value, payload)
      ElMessage.success('书目已更新')
    } else {
      await createBook(payload)
      ElMessage.success('书目已创建，可继续入库生成副本')
    }
    formVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    submitting.value = false
  }
}

async function removeBook(book: Book): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除《${book.title}》？有副本或借阅记录时后端会拒绝。`, '删除书目', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteBook(book.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  }
}

/* ---------------- 入库 ---------------- */

const intakeVisible = ref(false)
const intakeTarget = ref<Book | null>(null)
const intakeForm = reactive({ branch: null as number | null, quantity: 1, shelf: '' })
/** 入库是幂等操作：键在打开弹窗时生成，重试复用，成功后清空。 */
const intakeKey = ref('')

function openIntake(book: Book): void {
  intakeTarget.value = book
  intakeForm.branch = branches.value.find((item) => item.active)?.id ?? null
  intakeForm.quantity = 1
  intakeForm.shelf = ''
  intakeKey.value = newIdempotencyKey()
  intakeVisible.value = true
}

async function submitIntake(): Promise<void> {
  if (!intakeTarget.value || !intakeForm.branch) {
    ElMessage.warning('请选择入库网点')
    return
  }
  if (intakeForm.quantity < 1 || intakeForm.quantity > 500) {
    ElMessage.warning('数量需在 1~500 之间')
    return
  }
  submitting.value = true
  try {
    const result = await intakeCopies(
      intakeTarget.value.id,
      { branch: intakeForm.branch, quantity: intakeForm.quantity, shelf: intakeForm.shelf.trim() },
      intakeKey.value,
    )
    intakeKey.value = ''
    ElMessage.success(`已入库 ${result.copies.length} 册并分配 RFID`)
    intakeVisible.value = false
    await Promise.all([load(), ensureLoaded(true)])
  } catch (error) {
    // 失败保留键，重试不会重复入库。
    ElMessage.error(errorMessage(error, '入库失败'))
  } finally {
    submitting.value = false
  }
}

/* ---------------- 副本 ---------------- */

const copiesVisible = ref(false)
const copyTarget = ref<Book | null>(null)
const copies = ref<Copy[]>([])
const copiesLoading = ref(false)

async function openCopies(book: Book): Promise<void> {
  copyTarget.value = book
  copiesVisible.value = true
  copiesLoading.value = true
  try {
    const data = await searchCopies({ book: book.id })
    copies.value = data.results
  } catch (error) {
    copies.value = []
    ElMessage.error(errorMessage(error, '副本加载失败'))
  } finally {
    copiesLoading.value = false
  }
}

/**
 * 副本状态改变后，抽屉与书目列表都要刷新：
 * 书目的可借/总数由后端按副本状态统计，只刷抽屉会让列表停留在旧数字上。
 */
async function refreshCopies(): Promise<void> {
  if (!copyTarget.value) return
  await Promise.all([openCopies(copyTarget.value), load(), ensureLoaded(true).catch(() => undefined)])
}

async function handleDisinfect(copy: Copy): Promise<void> {
  try {
    await disinfectCopy(copy.id)
    ElMessage.success('已登记消毒')
    await refreshCopies()
  } catch (error) {
    ElMessage.error(errorMessage(error, '消毒登记失败'))
  }
}

async function handleShelve(copy: Copy): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('填写上架架位', '上架', {
      inputValue: copy.shelf,
      inputValidator: (text) => (text && text.trim() ? true : '架位不能为空'),
    })
    await shelveCopy(copy.id, value.trim())
    ElMessage.success('已上架，如该书有预约者将自动分配')
    await refreshCopies()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorMessage(error, '上架失败'))
  }
}

async function handleSetStatus(copy: Copy, status: 'withdrawn' | 'lost' | 'processing'): Promise<void> {
  const label = COPY_STATUS_LABEL[status]
  try {
    const { value } = await ElMessageBox.prompt(`将副本 ${copy.id} 标记为「${label}」，请填写原因`, '变更副本状态', {
      inputValidator: (text) => (text && text.trim() ? true : '原因必填'),
    })
    await setCopyStatus(copy.id, status, value.trim())
    ElMessage.success(`已标记为${label}`)
    await refreshCopies()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorMessage(error, '状态变更失败'))
  }
}

function statusTagType(status: CopyStatus): 'success' | 'info' | 'warning' | 'danger' {
  if (status === 'available') return 'success'
  if (status === 'lost' || status === 'withdrawn') return 'danger'
  if (status === 'processing' || status === 'transit') return 'warning'
  return 'info'
}
</script>

<template>
  <div class="lib-stack">
    <el-alert
      v-if="!auth.isAdmin"
      type="info"
      :closable="false"
      title="当前为运维账号"
      description="书目与入库仅管理员可操作；你仍可对副本登记消毒与上架。"
    />

    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          class="toolbar__search"
          clearable
          placeholder="书名、作者、ISBN、分类号或索书号"
          @keyup.enter="submitSearch"
          @clear="submitSearch"
        />
        <el-select v-model="categoryFilter" clearable placeholder="全部分类" class="toolbar__select" @change="submitSearch">
          <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-button type="primary" @click="submitSearch">查询</el-button>
        <el-button v-if="auth.isAdmin" type="success" @click="openCreate">新增书目</el-button>
      </div>

      <el-table v-loading="loading" :data="books" size="small" empty-text="暂无书目">
        <el-table-column label="书名" min-width="200">
          <template #default="{ row }">
            <div class="cell-title">{{ row.title }}</div>
            <div class="lib-text-muted cell-sub">{{ row.author }} · {{ row.isbn }}</div>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="120">
          <template #default="{ row }">{{ categoryName(row.category) }}</template>
        </el-table-column>
        <el-table-column prop="call_number" label="索书号" width="120" />
        <el-table-column label="定价" width="100">
          <template #default="{ row }">{{ formatMoney(row.price) }}</template>
        </el-table-column>
        <el-table-column label="馆藏" width="120">
          <template #default="{ row }">
            <span :class="{ 'cell-warn': row.total_count > 0 && row.available_count === 0 }">
              可借 {{ row.available_count }} / 共 {{ row.total_count }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="在借" width="80">
          <template #default="{ row }">{{ row.loaned_count }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'success' : 'info'" size="small" effect="plain">
              {{ row.active ? '在架' : '已下架' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" align="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openCopies(row)">副本</el-button>
            <template v-if="auth.isAdmin">
              <el-button text type="primary" size="small" @click="openIntake(row)">入库</el-button>
              <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button text type="danger" size="small" @click="removeBook(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

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

    <!-- 新增 / 编辑书目 -->
    <el-dialog v-model="formVisible" :title="formTitle" width="620px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="书名" required>
          <el-input v-model="form.title" maxlength="200" />
        </el-form-item>
        <el-form-item label="ISBN" required>
          <el-input v-model="form.isbn" maxlength="20" placeholder="唯一，重复会被拒绝" />
        </el-form-item>
        <el-form-item label="作者" required>
          <el-input v-model="form.author" maxlength="150" />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="form.category" placeholder="选择分类" class="dialog-select">
            <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="索书号" required>
          <el-input v-model="form.call_number" maxlength="50" placeholder="如 TP/001" />
        </el-form-item>
        <el-form-item label="定价">
          <el-input v-model="form.price" placeholder="如 59.00" />
        </el-form-item>
        <el-form-item label="出版社">
          <el-input v-model="form.publisher" maxlength="150" />
        </el-form-item>
        <el-form-item label="封面地址">
          <el-input v-model="form.cover" placeholder="图片 URL，可留空" />
        </el-form-item>
        <el-form-item label="在架">
          <el-switch v-model="form.active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 入库 -->
    <el-dialog v-model="intakeVisible" title="入库生成副本" width="520px">
      <p class="dialog-hint">{{ intakeTarget?.title }}</p>
      <el-form :model="intakeForm" label-width="90px">
        <el-form-item label="入库网点" required>
          <el-select v-model="intakeForm.branch" placeholder="选择网点" class="dialog-select">
            <el-option v-for="item in branches" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量" required>
          <el-input-number v-model="intakeForm.quantity" :min="1" :max="500" />
        </el-form-item>
        <el-form-item label="架位">
          <el-input v-model="intakeForm.shelf" maxlength="100" placeholder="如 A-01" />
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" title="每册都会分配唯一 RFID，库存数量由副本统计，不直接改书目上的数字。" />
      <template #footer>
        <el-button @click="intakeVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitIntake">确认入库</el-button>
      </template>
    </el-dialog>

    <!-- 副本列表 -->
    <el-drawer v-model="copiesVisible" :title="`副本 · ${copyTarget?.title ?? ''}`" size="720px">
      <el-table v-loading="copiesLoading" :data="copies" size="small" empty-text="暂无副本">
        <el-table-column prop="id" label="编号" width="70" />
        <el-table-column label="网点" width="130">
          <template #default="{ row }">{{ branchName(row.branch) }}</template>
        </el-table-column>
        <el-table-column prop="shelf" label="架位" width="90" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
              {{ COPY_STATUS_LABEL[row.status as Copy['status']] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="消毒时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.disinfected_at) }}</template>
        </el-table-column>
        <el-table-column label="RFID" min-width="200">
          <template #default="{ row }"><span class="cell-rfid">{{ row.rfid }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="270" align="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'processing'" text type="primary" size="small" @click="handleDisinfect(row)">
              消毒
            </el-button>
            <el-button v-if="row.status === 'processing'" text type="primary" size="small" @click="handleShelve(row)">
              上架
            </el-button>
            <template v-if="auth.isAdmin">
              <el-button
                v-if="row.status !== 'processing'"
                text
                type="primary"
                size="small"
                @click="handleSetStatus(row, 'processing')"
              >
                转待处理
              </el-button>
              <el-button
                v-if="row.status !== 'withdrawn' && row.status !== 'lost'"
                text
                type="danger"
                size="small"
                @click="handleSetStatus(row, 'withdrawn')"
              >
                下架
              </el-button>
              <el-button
                v-if="row.status !== 'lost' && row.status !== 'withdrawn'"
                text
                type="danger"
                size="small"
                @click="handleSetStatus(row, 'lost')"
              >
                报损
              </el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <p class="lib-text-muted dialog-hint">
        归还的副本默认进入待处理，需消毒并上架后才可再次外借；上架时若该书有预约者会自动分配。
      </p>
    </el-drawer>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.toolbar__search {
  max-width: 320px;
}

.toolbar__select {
  width: 150px;
}

.cell-title {
  font-weight: 600;
}

.cell-sub {
  font-size: 12px;
}

.cell-warn {
  color: #e6a23c;
}

.cell-rfid {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}

.pager {
  justify-content: center;
  margin-top: 16px;
}

.dialog-select {
  width: 100%;
}

.dialog-hint {
  margin: 0 0 12px;
}
</style>
