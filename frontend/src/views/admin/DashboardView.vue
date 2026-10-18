<script setup lang="ts">
/**
 * 运营大屏，对应 FR-44~FR-45。数据来自 reports/summary/（管理员与运维可读）。
 *
 * 可视化上的几个刻意选择：
 * - 全视图只有一个主数字（在馆人数），其余用数字卡片 —— 把「一个故事」和一堆指标分开。
 * - 分布与排行一律用「标签 · 条 · 数值」的行式布局，而不是条形图：演示数据里
 *   分类常常只有一两项，画成图就是「一根柱子的条形图」这类反模式，行式在任何条数下都成立。
 * - 趋势天数为 1~2 天时不画柱图，改用标签行 —— 一两根柱子不构成趋势。
 * - 单系列只用一种数据色，分类身份由行标签承载，因此不需要图例；
 *   数值与标签一律用文本色，不穿数据色。每行带 title 作为悬停提示。
 * - 告警等级用固定状态色，且始终与文字标签同时出现：浅色面上 warning/serious
 *   的对比度低于 3:1，不能只靠颜色表意。
 *
 * 在馆人数与空闲座位由人数估算得出，未连接座位传感器，页面如实标注。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorMessage, getAll } from '@/api/client'
import { COPY_STATUS_LABEL, fetchBranchOccupancy, type CopyStatus } from '@/api/books'
import {
  DEVICE_EVENT_LABEL,
  exportReportCsv,
  fetchReportSummary,
  type DeviceEventKind,
  type ReportSummary,
} from '@/api/iot'
import type { UserProfile } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useCatalog } from '@/composables/useCatalog'
import { formatMoney } from '@/utils/format'
import VizBarList from '@/components/VizBarList.vue'
import VizColumnChart from '@/components/VizColumnChart.vue'

const auth = useAuthStore()
const { branches, ensureLoaded } = useCatalog()

const summary = ref<ReportSummary | null>(null)
const occupancyByBranch = ref<{ label: string; value: number }[]>([])
const readerNames = ref<Map<number, string>>(new Map())
const loading = ref(false)
const exporting = ref(false)

/** 趋势不足 3 天就改渲染为标签行，避免「一两根柱子」的伪趋势。 */
const MIN_TREND_DAYS = 3

const heroOccupancy = computed(() => summary.value?.occupancy ?? 0)

const kpis = computed(() => {
  const data = summary.value
  if (!data) return []
  return [
    { label: '设备在线', value: `${data.devices_online} / ${data.devices_total}` },
    { label: '开放告警', value: String(data.open_alerts) },
    { label: '逾期借阅', value: String(data.overdue_loans) },
    { label: '罚款收入', value: formatMoney(data.fine_income) },
    { label: '押金余额', value: formatMoney(data.deposit_balance) },
    { label: '待上架超时', value: String(data.late_shelving) },
    { label: '逾期工单', value: String(data.overdue_workorders) },
    { label: '累计工时', value: String(data.labor_hours) },
  ]
})

const copiesByStatus = computed(() =>
  (summary.value?.copies_by_status ?? []).map((item) => ({
    label: COPY_STATUS_LABEL[item.status as CopyStatus] ?? item.status,
    value: item.count,
  })),
)

const categoryRows = computed(() =>
  (summary.value?.categories ?? []).map((item) => ({ label: item.book__category__name || '未分类', value: item.count })),
)

const popularRows = computed(() =>
  (summary.value?.popular_books ?? []).map((item) => ({ label: item.copy__book__title || `书目 ${item.copy__book_id}`, value: item.count })),
)

const readerRows = computed(() =>
  (summary.value?.reader_activity ?? [])
    .slice(0, 6)
    .map((item) => ({ label: readerNames.value.get(item.reader_id) ?? `读者 ${item.reader_id}`, value: item.count })),
)

const loanTrend = computed(() =>
  (summary.value?.loan_trend ?? []).map((item) => ({ label: item.day?.slice(5) ?? '—', value: item.count })),
)

const visitsTrend = computed(() =>
  (summary.value?.visits_trend ?? []).map((item) => ({ label: (item.day ?? '').slice(5) || '—', value: item.count ?? 0 })),
)

const deviceEventRows = computed(() =>
  (summary.value?.device_events ?? []).map((item) => ({
    label: DEVICE_EVENT_LABEL[item.kind as DeviceEventKind] ?? item.kind ?? '未分类',
    value: item.count ?? 0,
  })),
)

const costRows = computed(() =>
  (summary.value?.annual_costs ?? []).map((item) => ({
    label: item.kind ?? '其他',
    value: Number(item.amount ?? item.total ?? 0),
  })),
)

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await fetchReportSummary()
    summary.value = data
    // 各网点在馆人数：公开接口，逐网点取
    occupancyByBranch.value = await Promise.all(
      branches.value.map(async (branch) => {
        try {
          const occ = await fetchBranchOccupancy(branch.id)
          return { label: branch.name, value: occ.occupancy }
        } catch {
          return { label: branch.name, value: 0 }
        }
      }),
    )
  } catch (error) {
    summary.value = null
    ElMessage.error(errorMessage(error, '运营数据加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  void ensureLoaded().catch(() => undefined)
  // 读者活跃排行只带 reader_id，取读者列表换成可辨识的姓名。
  // readers/ 是 AdminOnly，运维会 403，此时退回显示「读者 N」。
  try {
    const readers = await getAll<UserProfile>('/readers/')
    readerNames.value = new Map(readers.map((item) => [item.id, item.first_name || item.phone]))
  } catch {
    readerNames.value = new Map()
  }
  await load()
})

async function exportCsv(): Promise<void> {
  exporting.value = true
  try {
    const blob = await exportReportCsv()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `馆藏导出_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出 CSV，导出行为已记入审计')
  } catch (error) {
    ElMessage.error(errorMessage(error, '导出失败'))
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="lib-stack">
    <el-alert
      v-if="!branches.length && !loading"
      type="warning"
      :closable="false"
      title="没有可用的网点数据，运营指标将为空。"
    />

    <div class="dash">
      <!-- 主数字：全视图唯一 -->
      <el-card shadow="never" class="hero">
        <p class="hero__label">当前在馆人数</p>
        <p class="hero__value">{{ heroOccupancy }}</p>
        <p class="hero__hint">空闲座位为按人数估算，未连接座位传感器</p>
      </el-card>

      <el-card shadow="never" class="kpis">
        <div class="kpi-grid">
          <div v-for="item in kpis" :key="item.label" class="kpi">
            <span class="kpi__label">{{ item.label }}</span>
            <span class="kpi__value">{{ item.value }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <div class="panels">
      <el-card shadow="never">
        <template #header>各网点在馆人数</template>
        <el-empty v-if="!occupancyByBranch.length" description="暂无网点" :image-size="70" />
        <VizBarList v-else :items="occupancyByBranch" unit=" 人" />
      </el-card>

      <el-card shadow="never">
        <template #header>馆藏状态分布</template>
        <el-empty v-if="!copiesByStatus.length" description="暂无馆藏" :image-size="70" />
        <VizBarList v-else :items="copiesByStatus" unit=" 册" />
      </el-card>

      <el-card shadow="never">
        <template #header>分类馆藏量</template>
        <el-empty v-if="!categoryRows.length" description="暂无分类统计" :image-size="70" />
        <VizBarList v-else :items="categoryRows" unit=" 册" />
      </el-card>

      <el-card shadow="never">
        <template #header>借阅量 TOP</template>
        <el-empty v-if="!popularRows.length" description="暂无借阅" :image-size="70" />
        <VizBarList v-else :items="popularRows" unit=" 次" />
      </el-card>

      <el-card shadow="never">
        <template #header>读者活跃度 TOP</template>
        <el-empty v-if="!readerRows.length" description="暂无读者活动" :image-size="70" />
        <VizBarList v-else :items="readerRows" unit=" 次" />
      </el-card>

      <el-card shadow="never">
        <template #header>设备事件统计</template>
        <el-empty v-if="!deviceEventRows.length" description="暂无设备事件" :image-size="70" />
        <VizBarList v-else :items="deviceEventRows" unit=" 条" />
      </el-card>
    </div>

    <div class="panels">
      <el-card shadow="never">
        <template #header>借阅趋势（按天）</template>
        <el-empty v-if="!loanTrend.length" description="暂无借阅数据" :image-size="70" />
        <VizColumnChart v-else-if="loanTrend.length >= MIN_TREND_DAYS" :items="loanTrend" unit=" 次" />
        <VizBarList v-else :items="loanTrend" unit=" 次" />
        <p v-if="loanTrend.length && loanTrend.length < MIN_TREND_DAYS" class="panel-hint">
          仅 {{ loanTrend.length }} 天数据，不足 3 天改用列表展示，避免一两根柱子被当成趋势。
        </p>
      </el-card>

      <el-card shadow="never">
        <template #header>客流趋势（按天）</template>
        <el-empty v-if="!visitsTrend.length" description="暂无进出馆记录" :image-size="70" />
        <VizColumnChart v-else-if="visitsTrend.length >= MIN_TREND_DAYS" :items="visitsTrend" unit=" 人次" />
        <VizBarList v-else :items="visitsTrend" unit=" 人次" />
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>年度成本构成</span>
          <el-tooltip :content="auth.isAdmin ? '' : 'CSV 导出仅管理员可用'" :disabled="auth.isAdmin" placement="top">
            <span>
              <el-button size="small" :disabled="!auth.isAdmin" :loading="exporting" @click="exportCsv">
                导出馆藏 CSV
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </template>
      <el-empty v-if="!costRows.length" description="暂无成本数据" :image-size="70" />
      <VizBarList v-else :items="costRows" />
      <p class="panel-hint">
        成本与工时来自运营记录（operations），服务费计算依据由运营方录入；累计工时 {{ summary?.labor_hours ?? 0 }}。
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.dash {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(240px, 1fr) 3fr;
}

.hero {
  background: linear-gradient(160deg, #f4f8ff, #ffffff 70%);
}

.hero__label {
  color: var(--lib-text-muted);
  margin: 0;
}

.hero__value {
  color: var(--lib-text);
  font-size: 56px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  line-height: 1.1;
  margin: 6px 0;
}

.hero__hint {
  color: var(--lib-text-muted);
  font-size: 12px;
  margin: 0;
}

.kpi-grid {
  display: grid;
  gap: 16px 18px;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
}

.kpi {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi__label {
  color: var(--lib-text-muted);
  font-size: 13px;
}

.kpi__value {
  color: var(--lib-text);
  font-size: 22px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.panels {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.card-head {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.panel-hint {
  color: var(--lib-text-muted);
  font-size: 12px;
  margin: 12px 0 0;
}

@media (max-width: 900px) {
  .dash {
    grid-template-columns: 1fr;
  }
}
</style>
