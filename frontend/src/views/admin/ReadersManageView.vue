<script setup lang="ts">
/**
 * 读者管理，仅管理员（后端 readers/ 为 AdminOnly，运维访问会 403）。
 *
 * 管理动作全部走 readers/{id}/manage/：冻结、角色、信用增减、押金增减、重置密码，
 * 且 reason 必填。两个要点：
 * 1. 只在用户确实改动时才提交对应字段 —— 传 credit_delta=0 会在后端生成一条
 *    金额为 0 的信用流水，等于制造噪音数据。
 * 2. 角色变更仅超级管理员可执行，前端拿不到 is_superuser，所以照常展示该字段，
 *    由后端拒绝并回显原因。
 *
 * 不提供「按读者查看流水」：后端 credit-entries/deposit-entries 没有 reader 过滤，
 * 传 ?reader= 会被静默忽略并返回全部记录，在前端展示会串成别人的数据。
 * 读者本人查看自己的流水走 ProfileView，那条路径由服务端按人过滤，是正确的。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import { listReaders, manageReader } from '@/api/readers'
import type { UserProfile } from '@/api/auth'
import type { Role } from '@/api/session'
import { formatMoney } from '@/utils/format'

const PAGE_SIZE = 20

const readers = ref<UserProfile[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const usernameSearch = ref('')
const phoneExact = ref('')
const roleFilter = ref<Role | ''>('')
const frozenFilter = ref<'' | 'true' | 'false'>('')

const roleOptions: { value: Role; label: string }[] = [
  { value: 'reader', label: '读者' },
  { value: 'admin', label: '管理员' },
  { value: 'operator', label: '运维' },
]

function roleLabel(role: Role): string {
  return roleOptions.find((item) => item.value === role)?.label ?? role
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listReaders({
      search: usernameSearch.value.trim(),
      // 手机号是确定性加密字段，只能精确匹配，不能模糊检索。
      phone: phoneExact.value.trim(),
      role: roleFilter.value,
      frozen: frozenFilter.value,
      page: page.value,
    })
    readers.value = data.results
    total.value = data.count
  } catch (error) {
    readers.value = []
    total.value = 0
    ElMessage.error(errorMessage(error, '读者列表加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

function submitSearch(): void {
  page.value = 1
  void load()
}

function resetFilters(): void {
  usernameSearch.value = ''
  phoneExact.value = ''
  roleFilter.value = ''
  frozenFilter.value = ''
  submitSearch()
}

function changePage(next: number): void {
  page.value = next
  void load()
}

/* ---------------- 管理读者 ---------------- */

const manageVisible = ref(false)
const target = ref<UserProfile | null>(null)
const submitting = ref(false)
const manageForm = reactive({
  frozen: false,
  role: 'reader' as Role,
  credit_delta: 0,
  deposit_delta: '0',
  new_password: '',
  reason: '',
})
/** 幂等：键在打开弹窗时生成，失败重试复用，成功后清空。 */
const manageKey = ref('')

function openManage(reader: UserProfile): void {
  target.value = reader
  manageForm.frozen = reader.frozen
  manageForm.role = reader.role
  manageForm.credit_delta = 0
  manageForm.deposit_delta = '0'
  manageForm.new_password = ''
  manageForm.reason = ''
  manageKey.value = newIdempotencyKey()
  manageVisible.value = true
}

async function submitManage(): Promise<void> {
  if (!target.value) return
  if (!manageForm.reason.trim()) {
    ElMessage.warning('请填写操作理由，理由会记入审计')
    return
  }

  // 只提交真正发生变化的字段，避免生成无意义的 0 金额流水。
  const payload: Parameters<typeof manageReader>[1] = { reason: manageForm.reason.trim() }
  if (manageForm.frozen !== target.value.frozen) payload.frozen = manageForm.frozen
  if (manageForm.role !== target.value.role) payload.role = manageForm.role
  if (manageForm.credit_delta !== 0) payload.credit_delta = manageForm.credit_delta
  if (Number(manageForm.deposit_delta) !== 0) payload.deposit_delta = manageForm.deposit_delta
  if (manageForm.new_password) payload.new_password = manageForm.new_password

  if (Object.keys(payload).length === 1) {
    ElMessage.warning('没有需要提交的变更')
    return
  }

  submitting.value = true
  try {
    await manageReader(target.value.id, payload, manageKey.value)
    manageKey.value = ''
    ElMessage.success('已提交，变更已记入审计')
    manageVisible.value = false
    await load()
  } catch (error) {
    // 失败保留幂等键，重试不会重复调整信用或押金。
    ElMessage.error(errorMessage(error, '操作失败'))
  } finally {
    submitting.value = false
  }
}

function creditTagType(level: UserProfile['credit_level']): 'success' | 'warning' | 'danger' {
  if (level === 'untrusted') return 'danger'
  if (level === 'restricted') return 'warning'
  return 'success'
}

function creditLevelText(level: UserProfile['credit_level']): string {
  if (level === 'untrusted') return '失信'
  if (level === 'restricted') return '受限'
  return '正常'
}
</script>

<template>
  <div class="lib-stack">
    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="usernameSearch"
          class="toolbar__search"
          clearable
          placeholder="用户名模糊检索"
          @keyup.enter="submitSearch"
        />
        <el-input
          v-model="phoneExact"
          class="toolbar__phone"
          clearable
          maxlength="11"
          placeholder="手机号（需完整精确）"
          @keyup.enter="submitSearch"
        />
        <el-select v-model="roleFilter" clearable placeholder="全部角色" class="toolbar__select" @change="submitSearch">
          <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="frozenFilter" clearable placeholder="全部状态" class="toolbar__select" @change="submitSearch">
          <el-option label="正常" value="false" />
          <el-option label="已冻结" value="true" />
        </el-select>
        <el-button type="primary" @click="submitSearch">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="readers" size="small" empty-text="暂无读者">
        <el-table-column label="手机号" width="140" prop="phone" />
        <el-table-column label="昵称" min-width="140">
          <template #default="{ row }">{{ row.first_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'reader' ? 'info' : 'warning'" size="small" effect="plain">
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="实名" width="90">
          <template #default="{ row }">
            <el-tag :type="row.verified ? 'success' : 'info'" size="small" effect="plain">
              {{ row.verified ? '已实名' : '未实名' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="信用" width="130">
          <template #default="{ row }">
            {{ row.credit }}
            <el-tag :type="creditTagType(row.credit_level)" size="small" effect="plain">
              {{ creditLevelText(row.credit_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="押金" width="110">
          <template #default="{ row }">{{ formatMoney(row.deposit) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="!row.is_active" type="info" size="small" effect="plain">已停用</el-tag>
            <el-tag v-else-if="row.frozen" type="danger" size="small" effect="plain">已冻结</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">正常</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openManage(row)">管理</el-button>
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

    <el-dialog v-model="manageVisible" title="管理读者" width="560px">
      <el-descriptions v-if="target" :column="2" border size="small" class="target">
        <el-descriptions-item label="手机号">{{ target.phone }}</el-descriptions-item>
        <el-descriptions-item label="昵称">{{ target.first_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="当前信用">{{ target.credit }}</el-descriptions-item>
        <el-descriptions-item label="当前押金">{{ formatMoney(target.deposit) }}</el-descriptions-item>
      </el-descriptions>

      <el-form :model="manageForm" label-width="100px">
        <el-form-item label="冻结账号">
          <el-switch v-model="manageForm.frozen" active-text="冻结后不可借阅" />
        </el-form-item>

        <el-form-item label="角色">
          <el-select v-model="manageForm.role" class="dialog-select">
            <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <span class="lib-text-muted field-hint">角色变更仅超级管理员可执行，否则后端会拒绝。</span>
        </el-form-item>

        <el-form-item label="信用调整">
          <el-input-number v-model="manageForm.credit_delta" :min="-200" :max="200" />
          <span class="lib-text-muted field-hint">0 表示不调整；调整会生成一条信用流水。</span>
        </el-form-item>

        <el-form-item label="押金调整">
          <el-input v-model="manageForm.deposit_delta" class="dialog-money" placeholder="如 50 或 -20" />
          <span class="lib-text-muted field-hint">0 表示不调整；余额不能为负。</span>
        </el-form-item>

        <el-form-item label="重置密码">
          <el-input v-model="manageForm.new_password" type="password" show-password placeholder="留空表示不重置" />
        </el-form-item>

        <el-form-item label="操作理由" required>
          <el-input v-model="manageForm.reason" maxlength="255" type="textarea" :rows="2" placeholder="必填，将记入操作审计" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="manageVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitManage">提交变更</el-button>
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

.toolbar__search {
  max-width: 190px;
}

.toolbar__phone {
  max-width: 190px;
}

.toolbar__select {
  width: 130px;
}

.pager {
  justify-content: center;
  margin-top: 16px;
}

.target {
  margin-bottom: 16px;
}

.dialog-select {
  width: 160px;
}

.dialog-money {
  width: 140px;
}

.field-hint {
  font-size: 12px;
  margin-left: 10px;
}
</style>
