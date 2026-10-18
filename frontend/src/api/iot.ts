/**
 * 物联侧接口：设备、设备事件与命令、告警、门禁进出、运营报表。
 * 对应 backend/library/api/{devices,operations,alerts?,reports}.py 与 visits 相关动作（刘经纬提供）。
 *
 * 几处必须如实表达的后端语义：
 * - 设备命令的 status='simulated' 只表示「已登记并签名」，不代表硬件已执行；
 *   真实设备控制需要命令消费与回执适配器。
 * - 门禁的入馆会校验信用、冻结、人数上限与重复入馆；出馆不受欠费限制。
 * - 在馆人数与空闲座位由人数估算得出，未连接座位传感器。
 */
import { get, post, postIdempotent, type Page } from './client'

/* ------------------- 设备 ------------------- */

export type DeviceKind = 'rfid' | 'gate' | 'camera' | 'sensor' | 'smoke' | 'terminal' | 'light' | 'ac'

export const DEVICE_KIND_LABEL: Record<DeviceKind, string> = {
  rfid: 'RFID 读写器',
  gate: '门禁',
  camera: '摄像头',
  sensor: '环境传感器',
  smoke: '烟感',
  terminal: '自助终端',
  light: '照明',
  ac: '空调',
}

export interface Device {
  id: number
  name: string
  kind: DeviceKind
  online: boolean
  last_seen: string | null
  /** 设备影子：由事件上报维护的最新状态 */
  shadow: Record<string, unknown>
  branch: number
  created_at: string
  updated_at: string
}

export type DeviceEventKind = 'heartbeat' | 'telemetry' | 'fault' | 'smoke' | 'help' | 'security' | 'rfid_exit' | 'inventory'

export const DEVICE_EVENT_LABEL: Record<DeviceEventKind, string> = {
  heartbeat: '心跳',
  telemetry: '遥测',
  fault: '故障',
  smoke: '烟感',
  help: '求助',
  security: '安防',
  rfid_exit: '未借出离馆',
  inventory: '盘点',
}

export interface DeviceEvent {
  id: number
  device: number
  /** 设备上报的唯一标识，用于去重 */
  event_id: string
  kind: DeviceEventKind
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type DeviceCommandName = 'power_on' | 'power_off' | 'restart' | 'unlock' | 'broadcast'

export const DEVICE_COMMAND_LABEL: Record<DeviceCommandName, string> = {
  power_on: '开机',
  power_off: '关机',
  restart: '重启',
  unlock: '门禁解锁',
  broadcast: '喊话',
}

export interface DeviceCommand {
  id: number
  device: number
  command: DeviceCommandName
  reason: string
  /** pending / simulated 等；simulated 只代表已登记，不代表硬件已执行 */
  status: string
  signature: string
  actor: number | null
  created_at: string
  updated_at: string
}

export function listDevices(params: { branch?: number; kind?: DeviceKind; page?: number } = {}): Promise<Page<Device>> {
  return get<Page<Device>>('/devices/', { params })
}

export function listDeviceEvents(params: { device?: number; kind?: DeviceEventKind; page?: number } = {}): Promise<Page<DeviceEvent>> {
  return get<Page<DeviceEvent>>('/device-events/', { params })
}

export function listDeviceCommands(params: { device?: number; page?: number } = {}): Promise<Page<DeviceCommand>> {
  return get<Page<DeviceCommand>>('/device-commands/', { params })
}

/** 下发远程指令。reason 必填，会与签名一起记入台账。 */
export function sendDeviceCommand(device: number, command: DeviceCommandName, reason: string, key?: string): Promise<DeviceCommand> {
  return postIdempotent<DeviceCommand>(`/devices/${device}/command/`, { command, reason }, key)
}

/* ------------------- 告警 ------------------- */

export type AlertSeverity = 'info' | 'warning' | 'critical'
export type AlertStatus = 'open' | 'acknowledged' | 'resolved'

export const ALERT_SEVERITY_LABEL: Record<AlertSeverity, string> = {
  info: '提示',
  warning: '警告',
  critical: '严重',
}

export const ALERT_STATUS_LABEL: Record<AlertStatus, string> = {
  open: '待处理',
  acknowledged: '已确认',
  resolved: '已关闭',
}

export interface Alert {
  id: number
  device: number | null
  branch: number
  severity: AlertSeverity
  kind: string
  message: string
  status: AlertStatus
  resolution: string
  created_at: string
  updated_at: string
}

export function listAlerts(params: { status?: AlertStatus; severity?: AlertSeverity; page?: number } = {}): Promise<Page<Alert>> {
  return get<Page<Alert>>('/alerts/', { params })
}

/** 告警流转：open → acknowledged → resolved。关闭时必须给出处理结论。 */
export function transitionAlert(id: number, status: 'acknowledged' | 'resolved', resolution?: string): Promise<Alert> {
  return post<Alert>(`/alerts/${id}/transition/`, resolution ? { status, resolution } : { status })
}

/* ------------------- 门禁与在馆人数 ------------------- */

export interface Visit {
  id: number
  reader: number
  /** 与 reader 同值，代表未出馆；出馆后由后端清空 */
  active_reader: number | null
  branch: number
  entered_at: string
  exited_at: string | null
  created_at: string
  updated_at: string
}

export interface AccessResult {
  id: number
  direction: 'enter' | 'exit'
  /** 本次操作后的在馆人数 */
  occupancy: number
}

export type AccessMethod = 'qr' | 'card' | 'face'

export const ACCESS_METHOD_LABEL: Record<AccessMethod, string> = {
  qr: '扫码',
  card: '刷卡',
  face: '人脸',
}

/**
 * 门禁通行。演示环境用已登录读者身份代替真实读卡器。
 * 入馆会校验信用、冻结、人数上限与重复入馆；人脸方式还需最新的生物识别同意。
 */
export function accessBranch(branch: number, direction: 'enter' | 'exit', method: AccessMethod, key: string): Promise<AccessResult> {
  return postIdempotent<AccessResult>('/visits/access/', { branch, direction, method }, key)
}

export function listVisits(params: { branch?: number; page?: number } = {}): Promise<Page<Visit>> {
  return get<Page<Visit>>('/visits/', { params })
}

/** 馆内紧急求助，会生成一条告警。 */
export function askForHelp(branch: number, message: string): Promise<unknown> {
  return post('/visits/help/', { branch, message })
}

/* ------------------- 运营报表 ------------------- */

export interface ReportSummary {
  copies_by_status: { status: string; count: number }[]
  categories: { book__category__name: string; count: number }[]
  loan_trend: { day: string; count: number }[]
  popular_books: { copy__book_id: number; copy__book__title: string; count: number }[]
  reader_activity: { reader_id: number; count: number }[]
  occupancy: number
  visits_trend: { day?: string; count?: number }[]
  devices_total: number
  devices_online: number
  device_events: { kind?: string; count?: number }[]
  open_alerts: number
  fine_income: string | number
  deposit_balance: string | number
  overdue_loans: number
  late_shelving: number
  overdue_workorders: number
  workorders_on_time: number
  annual_costs: { kind?: string; amount?: string; total?: string; count?: number }[]
  labor_hours: string | number
}

export function fetchReportSummary(): Promise<ReportSummary> {
  return get<ReportSummary>('/reports/summary/')
}

/**
 * 馆藏 CSV 导出，仅管理员（后端会写审计，且已做公式注入防护）。
 * 返回 Blob，由页面触发下载；不是 JSON，客户端的信封解包会原样透传。
 */
export function exportReportCsv(): Promise<Blob> {
  return get<Blob>('/reports/export/', { responseType: 'blob' })
}

// 在馆人数接口（branches/{id}/occupancy/）属于馆藏/网点域，已在 api/books.ts 里提供
// fetchBranchOccupancy，这里不再重复定义，避免同名类型与函数两处漂移。
