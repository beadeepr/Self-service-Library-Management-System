<script setup lang="ts">
/**
 * 设备状态，对应 FR-29 与 FR-40。
 *
 * 只读展示设备台账、在线状态与设备影子；远程指令可以下发，但要如实表达其含义：
 * 后端返回的 status='simulated' 只表示「已登记并签名」，不代表硬件已执行。
 * 真实设备控制需要命令消费与执行回执适配器，未接入时 pending 不等于执行完成。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import {
  DEVICE_COMMAND_LABEL,
  DEVICE_EVENT_LABEL,
  DEVICE_KIND_LABEL,
  listDeviceCommands,
  listDeviceEvents,
  listDevices,
  sendDeviceCommand,
  type Device,
  type DeviceCommand,
  type DeviceCommandName,
  type DeviceEvent,
  type DeviceEventKind,
  type DeviceKind,
} from '@/api/iot'
import { useCatalog } from '@/composables/useCatalog'
import { formatDateTime } from '@/utils/format'

const { branchName, ensureLoaded } = useCatalog()

const devices = ref<Device[]>([])
const events = ref<DeviceEvent[]>([])
const commands = ref<DeviceCommand[]>([])
const loading = ref(false)
const selected = ref<Device | null>(null)
const acting = ref(false)

/** 每台设备的指令幂等键：失败重试复用，成功后清空。 */
const commandKeys = new Map<number, string>()

const commandOptions: DeviceCommandName[] = ['unlock', 'restart', 'power_on', 'power_off', 'broadcast']

const onlineCount = computed(() => devices.value.filter((item) => item.online).length)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [devicePage, eventPage, commandPage] = await Promise.all([
      listDevices(),
      listDeviceEvents(),
      listDeviceCommands(),
    ])
    devices.value = devicePage.results
    events.value = eventPage.results
    commands.value = commandPage.results
  } catch (error) {
    devices.value = []
    events.value = []
    commands.value = []
    ElMessage.error(errorMessage(error, '设备数据加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void ensureLoaded().catch(() => undefined)
  void load()
})

function deviceName(id: number | null | undefined): string {
  if (id === null || id === undefined) return '未关联设备'
  return devices.value.find((item) => item.id === id)?.name ?? `设备 ${id}`
}

/** 设备影子是后端维护的状态快照，字段随设备类型变化，这里按原样列出。 */
function shadowText(shadow: Record<string, unknown>): string {
  const entries = Object.entries(shadow ?? {})
  if (!entries.length) return '暂无影子数据'
  return entries.map(([key, value]) => `${key}=${JSON.stringify(value)}`).join('  ')
}

function commandStatusType(status: string): 'success' | 'info' | 'warning' {
  if (status === 'simulated') return 'info'
  if (status === 'pending') return 'warning'
  return 'success'
}

function openCommand(device: Device): void {
  selected.value = device
  commandKeys.set(device.id, newIdempotencyKey())
}

async function sendCommand(device: Device, command: DeviceCommandName): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      `将对「${device.name}」下发「${DEVICE_COMMAND_LABEL[command]}」，请填写原因`,
      '下发设备指令',
      { inputValidator: (text) => (text && text.trim() ? true : '原因必填') },
    )
    acting.value = true
    const key = commandKeys.get(device.id) ?? newIdempotencyKey()
    commandKeys.set(device.id, key)
    const result = await sendDeviceCommand(device.id, command, value.trim(), key)
    commandKeys.delete(device.id)
    ElMessage.success(`指令已登记，当前状态：${result.status}（simulated 表示尚未由真实硬件执行）`)
    await load()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorMessage(error, '指令下发失败'))
  } finally {
    acting.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="lib-stack">
    <el-alert
      type="info"
      :closable="false"
      title="设备状态由心跳与超时监测维护；远程指令状态为 simulated 时仅代表已登记并签名，不代表硬件已执行。"
    />

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>设备台账（{{ devices.length }} 台）</span>
          <el-tag :type="onlineCount ? 'success' : 'info'" effect="plain">在线 {{ onlineCount }}</el-tag>
        </div>
      </template>

      <el-table :data="devices" size="small" empty-text="暂无设备">
        <el-table-column prop="name" label="设备" min-width="150" />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">{{ DEVICE_KIND_LABEL[row.kind as DeviceKind] ?? row.kind }}</template>
        </el-table-column>
        <el-table-column label="网点" width="140">
          <template #default="{ row }">{{ branchName(row.branch) }}</template>
        </el-table-column>
        <el-table-column label="在线" width="100">
          <template #default="{ row }">
            <el-tag :type="row.online ? 'success' : 'info'" size="small" effect="plain">
              {{ row.online ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后心跳" width="170">
          <template #default="{ row }">{{ formatDateTime(row.last_seen) }}</template>
        </el-table-column>
        <el-table-column label="设备影子" min-width="200">
          <template #default="{ row }">
            <span class="shadow">{{ shadowText(row.shadow) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="远程指令" width="150" align="right">
          <template #default="{ row }">
            <el-popover placement="left" width="220" trigger="click" @show="openCommand(row)">
              <template #reference>
                <el-button text type="primary" size="small">下发指令</el-button>
              </template>
              <div class="command-list">
                <el-button
                  v-for="command in commandOptions"
                  :key="command"
                  text
                  size="small"
                  :disabled="acting"
                  @click="sendCommand(row, command)"
                >
                  {{ DEVICE_COMMAND_LABEL[command] }}
                </el-button>
              </div>
            </el-popover>
          </template>
        </el-table-column>
      </el-table>
      <p v-if="selected" class="panel-hint">最近选择：{{ selected.name }}</p>
    </el-card>

    <div class="panels">
      <el-card shadow="never">
        <template #header>最近设备事件</template>
        <el-table :data="events" size="small" empty-text="暂无事件">
          <el-table-column label="设备" width="130">
            <template #default="{ row }">{{ deviceName(row.device) }}</template>
          </el-table-column>
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ DEVICE_EVENT_LABEL[row.kind as DeviceEventKind] ?? row.kind }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="载荷" min-width="180">
            <template #default="{ row }"><span class="shadow">{{ JSON.stringify(row.payload) }}</span></template>
          </el-table-column>
          <el-table-column label="上报时间" width="170">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>指令台账</template>
        <el-table :data="commands" size="small" empty-text="暂无指令">
          <el-table-column label="设备" width="130">
            <template #default="{ row }">{{ deviceName(row.device) }}</template>
          </el-table-column>
          <el-table-column label="指令" width="110">
            <template #default="{ row }">
              {{ DEVICE_COMMAND_LABEL[row.command as DeviceCommandName] ?? row.command }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="commandStatusType(row.status)" size="small" effect="plain">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="160" />
          <el-table-column label="下发时间" width="170">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.card-head {
  align-items: center;
  display: flex;
  gap: 10px;
}

.panels {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
}

.shadow {
  color: var(--lib-text-muted);
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}

.command-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel-hint {
  color: var(--lib-text-muted);
  font-size: 12px;
  margin: 10px 0 0;
}
</style>
