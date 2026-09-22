<script setup lang="ts">
/**
 * 我的预约，对应 FR-21~FR-23。
 *
 * 预约不是「排队等位」而是「等一本书的副本被还回并上架」：
 * 后端在副本上架时（assign_hold）把最早的 waiting 预约置为 ready、绑定该副本、
 * 给出保留截止时间，并发一条到馆通知。所以 waiting 阶段没有副本也没有保留期，
 * 页面必须如实展示这一点，不能假装有排队位次（后端也没有返回该字段）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import {
  RESERVATION_STATUS_LABEL,
  cancelReservation,
  collectReservation,
  listReservations,
  type Reservation,
  type ReservationStatus,
} from '@/api/reservations'
import { useCatalog } from '@/composables/useCatalog'
import { daysUntil, formatDateTime } from '@/utils/format'

const router = useRouter()
const { branchName, bookOf, ensureLoaded } = useCatalog()

const reservations = ref<Reservation[]>([])
const loading = ref(false)
const actingId = ref<number | null>(null)

/** 每笔预约保留一个幂等键：失败重试复用，成功后清除，避免重复取书/重复取消。 */
const actionKeys = new Map<string, string>()

function keyFor(action: string, id: number): string {
  const name = `${action}:${id}`
  const key = actionKeys.get(name) ?? newIdempotencyKey()
  actionKeys.set(name, key)
  return key
}

const readyList = computed(() => reservations.value.filter((item) => item.status === 'ready'))
const hasHistory = computed(() => reservations.value.length > 0)

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listReservations()
    reservations.value = data.results
  } catch (error) {
    reservations.value = []
    ElMessage.error(errorMessage(error, '预约记录加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void ensureLoaded().catch(() => undefined)
  void load()
})

function statusTagType(status: ReservationStatus): 'success' | 'info' | 'warning' | 'danger' {
  if (status === 'ready') return 'success'
  if (status === 'waiting') return 'warning'
  if (status === 'expired') return 'danger'
  return 'info'
}

/** 保留期剩余描述，仅在 ready 且有 expires_at 时可用。 */
function holdText(item: Reservation): string {
  if (!item.expires_at) return ''
  const days = daysUntil(item.expires_at)
  if (days < 0) return `保留期已过（${formatDateTime(item.expires_at)}）`
  if (days === 0) return `今天最后一天（至 ${formatDateTime(item.expires_at)}）`
  return `保留至 ${formatDateTime(item.expires_at)}，剩余 ${days} 天`
}

async function collect(item: Reservation): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认取走《${bookOf(item.book)?.title ?? '该书'}》？取书后会立即生成借阅记录。`,
      '取书',
      { type: 'info' },
    )
  } catch {
    return
  }
  actingId.value = item.id
  try {
    const result = await collectReservation(item.id, keyFor('collect', item.id))
    actionKeys.delete(`collect:${item.id}`)
    ElMessage.success(`取书成功，应还日期 ${formatDateTime(result.due_at)}`)
    await Promise.all([load(), ensureLoaded(true).catch(() => undefined)])
  } catch (error) {
    ElMessage.error(errorMessage(error, '取书失败'))
  } finally {
    actingId.value = null
  }
}

async function cancel(item: Reservation): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认取消对《${bookOf(item.book)?.title ?? '该书'}》的预约？`, '取消预约', {
      type: 'warning',
    })
  } catch {
    return
  }
  actingId.value = item.id
  try {
    await cancelReservation(item.id, keyFor('cancel', item.id))
    actionKeys.delete(`cancel:${item.id}`)
    ElMessage.success('预约已取消')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '取消失败'))
  } finally {
    actingId.value = null
  }
}

const canAct = (item: Reservation): boolean => item.status === 'waiting' || item.status === 'ready'
</script>

<template>
  <div class="lib-stack">
    <el-card v-if="readyList.length" shadow="never" class="ready-card">
      <template #header>
        <div class="ready-head">
          <span>到馆待取</span>
          <el-tag type="success" effect="plain">{{ readyList.length }} 本</el-tag>
        </div>
      </template>

      <div v-for="item in readyList" :key="item.id" class="ready-item">
        <div>
          <p class="ready-item__title">{{ bookOf(item.book)?.title ?? `书目 ${item.book}` }}</p>
          <p class="lib-text-muted">
            取书网点 {{ branchName(item.branch) }}
            <template v-if="item.copy"> · 副本 {{ item.copy }}</template>
          </p>
          <p class="ready-item__hold">{{ holdText(item) }}</p>
        </div>
        <el-button type="primary" :loading="actingId === item.id" @click="collect(item)">取书</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>预约记录</template>

      <el-empty v-if="!loading && !hasHistory" description="暂无预约">
        <el-button type="primary" @click="router.push({ name: 'reader-search' })">去找书</el-button>
      </el-empty>

      <el-table v-else v-loading="loading" :data="reservations" size="small" empty-text="暂无预约">
        <el-table-column label="书名" min-width="200">
          <template #default="{ row }">
            <div class="cell-title">{{ bookOf(row.book)?.title ?? `书目 ${row.book}` }}</div>
            <div class="lib-text-muted cell-sub">{{ bookOf(row.book)?.author || '佚名' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="取书网点" width="140">
          <template #default="{ row }">{{ branchName(row.branch) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
              {{ RESERVATION_STATUS_LABEL[row.status as ReservationStatus] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="保留期" width="220">
          <template #default="{ row }">
            <span v-if="row.expires_at">{{ holdText(row) }}</span>
            <span v-else class="lib-text-muted">等有副本上架后分配</span>
          </template>
        </el-table-column>
        <el-table-column label="预约时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="right">
          <template #default="{ row }">
            <el-button
              v-if="canAct(row)"
              text
              type="danger"
              size="small"
              :loading="actingId === row.id"
              @click="cancel(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <p class="lib-text-muted hint">
        预约后需等该书的在借副本归还并消毒上架，才会分配给你并发送到馆通知；到馆后请在保留期内取书，逾期未取会自动释放。
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.ready-card {
  border-left: 4px solid #67c23a;
}

.ready-head {
  align-items: center;
  display: flex;
  gap: 8px;
}

.ready-item {
  align-items: center;
  border-bottom: 1px solid var(--lib-border);
  display: flex;
  justify-content: space-between;
  padding: 12px 0;
}

.ready-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.ready-item__title {
  font-size: 16px;
  font-weight: 700;
  margin: 0 0 4px;
}

.ready-item__hold {
  color: #67c23a;
  margin: 4px 0 0;
}

.cell-title {
  font-weight: 600;
}

.cell-sub {
  font-size: 12px;
}

.hint {
  margin: 14px 0 0;
}
</style>
