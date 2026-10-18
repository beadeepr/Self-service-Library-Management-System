<script setup lang="ts">
/**
 * 告警中心，对应 FR-30~FR-33。
 *
 * 告警流转：待处理 → 已确认 → 已关闭，关闭时必须填写处理结论（后端校验）。
 * 烟感一类的事件在生成告警的同时会创建维修工单并留下门禁联动指令，这里把关联工单
 * 一并展示，但不做流转 —— 工单由运营侧处理，本页只负责「看得见」。
 *
 * 等级用固定状态色，且**始终与文字标签同时出现**：浅色面上 warning 的对比度低于 3:1，
 * 不能只靠颜色表意；info 级别不构成告警，用中性文字而非状态色，避免状态色被滥用。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage } from '@/api/client'
import {
  ALERT_SEVERITY_LABEL,
  ALERT_STATUS_LABEL,
  listAlerts,
  listDevices,
  transitionAlert,
  type Alert,
  type AlertSeverity,
  type AlertStatus,
  type Device,
} from '@/api/iot'
import { useCatalog } from '@/composables/useCatalog'
import { formatDateTime } from '@/utils/format'

const { branchName, ensureLoaded } = useCatalog()

const alerts = ref<Alert[]>([])
const devices = ref<Device[]>([])
const loading = ref(false)
const statusFilter = ref<AlertStatus | ''>('open')
const actingId = ref<number | null>(null)

const statusOptions: { value: AlertStatus | ''; label: string }[] = [
  { value: 'open', label: '待处理' },
  { value: 'acknowledged', label: '已确认' },
  { value: 'resolved', label: '已关闭' },
  { value: '', label: '全部' },
]

const openCount = computed(() => alerts.value.filter((item) => item.status === 'open').length)
const criticalCount = computed(() => alerts.value.filter((item) => item.severity === 'critical' && item.status !== 'resolved').length)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [alertPage, devicePage] = await Promise.all([
      listAlerts(statusFilter.value ? { status: statusFilter.value } : {}),
      listDevices(),
    ])
    alerts.value = alertPage.results
    devices.value = devicePage.results
  } catch (error) {
    alerts.value = []
    ElMessage.error(errorMessage(error, '告警加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void ensureLoaded().catch(() => undefined)
  void load()
})

function deviceName(id: number | null): string {
  if (id === null) return '未关联设备'
  return devices.value.find((item) => item.id === id)?.name ?? `设备 ${id}`
}

function severityLabel(severity: AlertSeverity): string {
  return ALERT_SEVERITY_LABEL[severity] ?? severity
}

async function acknowledge(alert: Alert): Promise<void> {
  actingId.value = alert.id
  try {
    await transitionAlert(alert.id, 'acknowledged')
    ElMessage.success('已确认，仍待处理完成')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '确认失败'))
  } finally {
    actingId.value = null
  }
}

async function resolve(alert: Alert): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请填写处理结论，关闭告警时必须说明', '关闭告警', {
      inputType: 'textarea',
      inputValidator: (text) => (text && text.trim() ? true : '处理结论必填'),
    })
    actingId.value = alert.id
    await transitionAlert(alert.id, 'resolved', value.trim())
    ElMessage.success('告警已关闭')
    await load()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorMessage(error, '关闭失败'))
  } finally {
    actingId.value = null
  }
}
</script>

<template>
  <div v-loading="loading" class="lib-stack">
    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button v-for="item in statusOptions" :key="item.label" :value="item.value">
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
        <div class="toolbar__stats">
          <span class="lib-text-muted">待处理 {{ openCount }}</span>
          <span v-if="criticalCount" class="stat-critical">严重未关闭 {{ criticalCount }}</span>
        </div>
      </div>

      <el-table :data="alerts" size="small" empty-text="暂无告警">
        <el-table-column label="等级" width="110">
          <template #default="{ row }">
            <span class="sev" :class="`sev--${row.severity}`">
              <span class="sev__dot" />{{ severityLabel(row.severity) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="内容" min-width="200" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }"><span class="mono">{{ row.kind }}</span></template>
        </el-table-column>
        <el-table-column label="设备" width="130">
          <template #default="{ row }">{{ deviceName(row.device) }}</template>
        </el-table-column>
        <el-table-column label="网点" width="130">
          <template #default="{ row }">{{ branchName(row.branch) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">{{ ALERT_STATUS_LABEL[row.status as AlertStatus] ?? row.status }}</template>
        </el-table-column>
        <el-table-column label="发生时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="处理结论" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'lib-text-muted': !row.resolution }">{{ row.resolution || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="right">
          <template #default="{ row }">
            <!--
              严格按后端状态机给出下一步动作：open → 只能「确认」，acknowledged → 才能「关闭」。
              之前对 open 也显示「关闭」，点了会被后端以「告警必须先确认再关闭」拒绝。
            -->
            <el-button
              v-if="row.status === 'open'"
              text
              type="primary"
              size="small"
              :loading="actingId === row.id"
              @click="acknowledge(row)"
            >
              确认
            </el-button>
            <el-button
              v-else-if="row.status === 'acknowledged'"
              text
              type="danger"
              size="small"
              :loading="actingId === row.id"
              @click="resolve(row)"
            >
              关闭
            </el-button>
            <span v-else class="lib-text-muted">已结束</span>
          </template>
        </el-table-column>
      </el-table>

      <p class="panel-hint">
        关闭告警必须填写处理结论，处理记录写入审计。烟感等事件会在生成告警的同时创建维修工单并登记门禁联动指令，
        可在「设备状态」页查看指令台账。
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 14px;
}

.toolbar__stats {
  display: flex;
  gap: 14px;
}

.stat-critical {
  color: var(--viz-status-critical);
  font-weight: 600;
}

/* 等级标识：状态色 + 文字标签同时出现，颜色不单独表意 */
.sev {
  align-items: center;
  display: inline-flex;
  gap: 6px;
  white-space: nowrap;
}

.sev__dot {
  background: currentcolor;
  border-radius: 50%;
  height: 8px;
  width: 8px;
}

.sev--info {
  color: var(--lib-text-muted);
}

.sev--warning {
  color: #8a5a00;
}

.sev--warning .sev__dot {
  background: var(--viz-status-warning);
}

.sev--critical {
  color: var(--viz-status-critical);
  font-weight: 600;
}

.mono {
  color: var(--lib-text-muted);
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}

.panel-hint {
  color: var(--lib-text-muted);
  font-size: 12px;
  margin: 14px 0 0;
}
</style>
