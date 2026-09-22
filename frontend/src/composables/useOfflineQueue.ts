/**
 * 离线队列的界面侧封装：断网时询问入队、查看待补传、手动补传。
 *
 * 补传权限的边界要在提示里说清：后端仅允许管理员补传，读者身份的终端调用会被拒绝，
 * 此时如实报错，不假装成功。这一点见 kiosk/offline-queue.ts 的说明。
 */
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, errorMessage } from '@/api/client'
import { clearQueued, enqueue, listQueued, syncNow, type OfflineTransaction } from '@/kiosk/offline-queue'

/** 判定为「网络不可达」而非业务失败：客户端在无响应时给出 code=-1。 */
export function isNetworkFailure(error: unknown): boolean {
  return error instanceof ApiError && error.code === -1
}

export function useOfflineQueue() {
  const items = ref<OfflineTransaction[]>([])
  const syncing = ref(false)
  const clearing = ref(false)

  async function refresh(): Promise<void> {
    try {
      items.value = await listQueued()
    } catch {
      items.value = []
    }
  }

  /** 断网时询问是否把本次交易存入本机队列。返回是否已入队。 */
  async function offerOnNetworkFailure(input: Omit<OfflineTransaction, 'event_id' | 'occurred_at' | 'sync'>): Promise<boolean> {
    try {
      await ElMessageBox.confirm(
        '当前无法连接服务器，无法确认这笔交易是否已被受理。可将它存入本机离线队列，待网络恢复后再补传校验。',
        '网络不可用',
        { type: 'warning', confirmButtonText: '存入离线队列', cancelButtonText: '放弃' },
      )
    } catch {
      return false
    }
    try {
      await enqueue(input)
      await refresh()
      ElMessage.success('已存入本机离线队列，网络恢复后可在终端首页补传')
      return true
    } catch (error) {
      ElMessage.error(errorMessage(error, '写入离线队列失败'))
      return false
    }
  }

  async function sync(): Promise<void> {
    syncing.value = true
    try {
      const result = await syncNow()
      await refresh()
      if (!result.applied && !result.conflict) {
        ElMessage.info('没有待补传的交易')
        return
      }
      const detail = result.messages.length ? `；冲突原因：${result.messages.slice(0, 2).join('、')}` : ''
      ElMessage.success(`补传完成：成功 ${result.applied} 笔，冲突 ${result.conflict} 笔${detail}`)
    } catch (error) {
      // 最常见的失败是权限不足：补传接口仅管理员可用。
      ElMessage.error(errorMessage(error, '补传失败（补传接口仅管理员可用）'))
    } finally {
      syncing.value = false
    }
  }

  async function clear(): Promise<void> {
    clearing.value = true
    try {
      await clearQueued()
      await refresh()
      ElMessage.success('已清空本机离线队列')
    } catch (error) {
      ElMessage.error(errorMessage(error, '清空失败'))
    } finally {
      clearing.value = false
    }
  }

  return { items, syncing, clearing, refresh, offerOnNetworkFailure, sync, clear }
}
