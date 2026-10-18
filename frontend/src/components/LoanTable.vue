<script setup lang="ts">
/**
 * 借阅记录表格，读者端「我的借阅」与管理端共用。
 *
 * 借阅记录只有 copy 外键，没有书名，所以这里通过对照数据做 loan.copy → copy.book → book 映射；
 * 映射不到时退化为显示副本编号，而不是显示空白。
 */
import type { Loan } from '@/api/circulation'
import { useCatalog } from '@/composables/useCatalog'
import { dueDescription, formatDateTime } from '@/utils/format'

defineProps<{
  loans: Loan[]
  loading?: boolean
}>()

const { bookOfLoanCopy, copyOf, branchName } = useCatalog()

interface LoanStatus {
  type: 'success' | 'warning' | 'danger' | 'info'
  text: string
}

function statusOf(loan: Loan): LoanStatus {
  if (loan.returned_at) return { type: 'info', text: '已归还' }
  const due = dueDescription(loan.due_at)
  if (due.overdue) return { type: 'danger', text: due.text }
  if (due.text === '今天到期') return { type: 'warning', text: due.text }
  return { type: 'success', text: due.text }
}
</script>

<template>
  <el-table v-loading="loading" :data="loans" size="small" empty-text="暂无借阅记录">
    <el-table-column label="书名" min-width="220">
      <template #default="{ row }">
        <div class="loan-book">{{ bookOfLoanCopy(row.copy)?.title ?? `副本 ${row.copy}` }}</div>
        <div class="lib-text-muted loan-sub">
          {{ bookOfLoanCopy(row.copy)?.author || '佚名' }}
          <template v-if="copyOf(row.copy)">
            · {{ branchName(copyOf(row.copy)?.branch) }} {{ copyOf(row.copy)?.shelf }} 架
          </template>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="借出时间" width="160">
      <template #default="{ row }">{{ formatDateTime(row.borrowed_at) }}</template>
    </el-table-column>

    <el-table-column label="应还时间" width="160">
      <template #default="{ row }">{{ formatDateTime(row.due_at) }}</template>
    </el-table-column>

    <el-table-column label="归还时间" width="160">
      <template #default="{ row }">{{ formatDateTime(row.returned_at) }}</template>
    </el-table-column>

    <el-table-column label="状态" width="120">
      <template #default="{ row }">
        <el-tag :type="statusOf(row).type" size="small" effect="plain">{{ statusOf(row).text }}</el-tag>
      </template>
    </el-table-column>

    <el-table-column label="已续借" width="90">
      <template #default="{ row }">{{ row.renewals }} 次</template>
    </el-table-column>

    <!--
      操作列由使用方自己声明，而不是在这里开一个带 :loan 的插槽。
      原因是 el-table 的单元格渲染与父级插槽函数配合时，跨组件传下来的行对象不可靠
      （实测拿到的是空对象）。让使用方直接写 <el-table-column>，它拿到的 row 由 el-table
      直接提供，与其他列完全一致。
    -->
    <slot name="columns" />
  </el-table>
</template>

<style scoped>
.loan-book {
  font-weight: 600;
}

.loan-sub {
  font-size: 12px;
}
</style>
