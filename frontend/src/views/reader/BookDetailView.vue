<script setup lang="ts">
/**
 * 图书详情，对应 FR-09~FR-11。
 *
 * 关键概念：Book 是书目，Copy 是可流通的物理副本。详情页要按书目查出副本，
 * 读者关心的「能不能借、在哪个馆哪个架位」都来自副本，而不是书目上的计数。
 * 计数（available_count 等）由后端统计，这里不重算。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { COPY_STATUS_LABEL, fetchBook, searchCopies, type Book, type Copy } from '@/api/books'
import { errorMessage, newIdempotencyKey } from '@/api/client'
import { createReservation } from '@/api/reservations'
import { useAuthStore } from '@/stores/auth'
import { useCatalog } from '@/composables/useCatalog'
import { formatMoney } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { branchName, categoryName, ensureLoaded } = useCatalog()

const book = ref<Book | null>(null)
const copies = ref<Copy[]>([])
const loading = ref(false)

/* ---------- 预约 ---------- */

const reserveVisible = ref(false)
const reserveBranch = ref<number | null>(null)
const reserving = ref(false)
/** 幂等：键在打开预约弹窗时生成，失败重试复用，成功后清空。 */
const reserveKey = ref('')

interface BranchGroup {
  branch: number
  name: string
  total: number
  available: number
  items: Copy[]
}

/** 按网点分组展示副本位置：读者真正需要的是「去哪个馆、哪个架位」。 */
const groups = computed<BranchGroup[]>(() => {
  const grouped = new Map<number, Copy[]>()
  for (const copy of copies.value) {
    const bucket = grouped.get(copy.branch)
    if (bucket) bucket.push(copy)
    else grouped.set(copy.branch, [copy])
  }
  return [...grouped.entries()]
    .map(([branch, items]) => ({
      branch,
      name: branchName(branch),
      total: items.length,
      available: items.filter((item) => item.status === 'available').length,
      items,
    }))
    .sort((left, right) => right.available - left.available || left.name.localeCompare(right.name))
})

/**
 * 可预约的取书网点：只列「持有该书副本、但当前一本都不可借」的网点，
 * 因为后端就是按选定取书馆的借出/可借情况判定能否预约的，
 * 把没有副本或还有可借副本的网点列出来只会让读者点了被拒。
 */
const reservableBranches = computed(() => groups.value.filter((group) => group.total > 0 && group.available === 0))

/** 后端给出的 can_reserve 已经综合了在架与库存，前端只补登录态判断。 */
const canReserve = computed(() => !!book.value?.can_reserve && reservableBranches.value.length > 0)

const reserveHint = computed(() => {
  if (!book.value) return ''
  if (!book.value.active) return '该图书已下架，不可预约'
  if (book.value.available_count > 0) return '当前有可借副本，无需预约'
  if (!reservableBranches.value.length) return '该书副本正在处理中，暂不可预约'
  if (!auth.isAuthenticated) return '登录后可预约'
  return ''
})

function openReserve(): void {
  if (!auth.isAuthenticated) {
    ElMessage.warning('请先登录后再预约')
    void router.push({ name: 'reader-login', query: { redirect: route.fullPath } })
    return
  }
  // 默认选第一个可预约网点，通常就是唯一持有的那个馆。
  reserveBranch.value = reservableBranches.value[0]?.branch ?? null
  reserveKey.value = newIdempotencyKey()
  reserveVisible.value = true
}

async function submitReserve(): Promise<void> {
  if (!book.value || !reserveBranch.value) {
    ElMessage.warning('请选择取书网点')
    return
  }
  reserving.value = true
  try {
    await createReservation(book.value.id, reserveBranch.value, reserveKey.value)
    reserveKey.value = ''
    reserveVisible.value = false
    ElMessage.success('预约成功，等有副本归还并上架后会发到馆通知')
    await router.push({ name: 'reader-reservations' })
  } catch (error) {
    // 失败保留幂等键，重试不会重复预约。
    ElMessage.error(errorMessage(error, '预约失败'))
  } finally {
    reserving.value = false
  }
}

async function load(id: string): Promise<void> {
  loading.value = true
  try {
    const [detail, copyPage] = await Promise.all([fetchBook(id), searchCopies({ book: Number(id) })])
    book.value = detail
    copies.value = copyPage.results
  } catch (error) {
    book.value = null
    copies.value = []
    ElMessage.error(errorMessage(error, '图书详情加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void ensureLoaded().catch(() => undefined)
  void load(String(route.params.id))
})

// 从检索结果直接跳到另一本书时组件会复用，必须跟着参数重新拉取。
watch(
  () => route.params.id,
  (id) => {
    if (id) void load(String(id))
  },
)

function statusTagType(status: Copy['status']): 'success' | 'info' | 'warning' | 'danger' {
  if (status === 'available') return 'success'
  if (status === 'lost' || status === 'withdrawn') return 'danger'
  if (status === 'processing' || status === 'transit') return 'warning'
  return 'info'
}
</script>

<template>
  <div v-loading="loading" class="lib-stack">
    <el-page-header @back="router.back()">
      <template #content>
        <span>{{ book?.title ?? '图书详情' }}</span>
      </template>
    </el-page-header>

    <el-card v-if="book" shadow="never">
      <div class="detail">
        <div class="detail__cover">
          <img v-if="book.cover" :src="book.cover" :alt="book.title" />
          <span v-else>{{ book.title.slice(0, 1) }}</span>
        </div>

        <div class="detail__info">
          <h2 class="detail__title">{{ book.title }}</h2>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="作者">{{ book.author || '佚名' }}</el-descriptions-item>
            <el-descriptions-item label="出版社">{{ book.publisher || '未录入' }}</el-descriptions-item>
            <el-descriptions-item label="ISBN">{{ book.isbn || '未录入' }}</el-descriptions-item>
            <el-descriptions-item label="分类">{{ categoryName(book.category) }}</el-descriptions-item>
            <el-descriptions-item label="索书号">{{ book.call_number || '未录入' }}</el-descriptions-item>
            <el-descriptions-item label="定价">{{ formatMoney(book.price) }}</el-descriptions-item>
            <el-descriptions-item label="馆藏状态">
              <el-tag v-if="!book.active" type="info" size="small" effect="plain">已下架</el-tag>
              <el-tag v-else-if="book.available_count > 0" type="success" size="small" effect="plain">
                可借 {{ book.available_count }} 册
              </el-tag>
              <el-tag v-else type="warning" size="small" effect="plain">暂无可借</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="馆藏总量">
              共 {{ book.total_count }} 册，在借 {{ book.loaned_count }} 册
            </el-descriptions-item>
          </el-descriptions>

          <div class="detail__actions">
            <el-tooltip :content="reserveHint" :disabled="!reserveHint" placement="top">
              <span>
                <el-button :disabled="!canReserve" @click="openReserve">预约</el-button>
              </span>
            </el-tooltip>
            <el-button type="primary" @click="router.push({ name: 'reader-search' })">继续检索</el-button>
            <el-button
              v-if="auth.isAuthenticated"
              text
              type="primary"
              @click="router.push({ name: 'reader-reservations' })"
            >
              我的预约
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 预约取书网点 -->
    <el-dialog v-model="reserveVisible" title="预约图书" width="480px">
      <p class="reserve-book">{{ book?.title }}</p>
      <el-form label-width="90px">
        <el-form-item label="取书网点" required>
          <el-select v-model="reserveBranch" class="reserve-select" placeholder="选择取书网点">
            <el-option
              v-for="group in reservableBranches"
              :key="group.branch"
              :label="`${group.name}（${group.total} 册均在借）`"
              :value="group.branch"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        title="预约后需等该网点有副本归还并消毒上架，才会分配给你并发送到馆通知；到馆后请在保留期内取书。"
      />
      <template #footer>
        <el-button @click="reserveVisible = false">取消</el-button>
        <el-button type="primary" :loading="reserving" @click="submitReserve">确认预约</el-button>
      </template>
    </el-dialog>

    <el-card v-if="book" shadow="never">
      <template #header>馆藏位置（{{ copies.length }} 册）</template>

      <el-empty v-if="!copies.length" description="暂无副本记录" :image-size="70" />

      <el-collapse v-else>
        <el-collapse-item v-for="group in groups" :key="group.branch" :name="group.branch">
          <template #title>
            <span class="group-title">
              {{ group.name }}
              <el-tag :type="group.available > 0 ? 'success' : 'info'" size="small" effect="plain">
                可借 {{ group.available }} / {{ group.total }}
              </el-tag>
            </span>
          </template>

          <el-table :data="group.items" size="small">
            <el-table-column prop="shelf" label="架位" width="120" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
                  {{ COPY_STATUS_LABEL[row.status as Copy['status']] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="rfid" label="RFID" min-width="260" />
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-empty v-if="!loading && !book" description="没有找到这本书" />
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  gap: 24px;
}

.detail__cover {
  align-items: center;
  background: var(--lib-brand-soft);
  border-radius: var(--lib-radius);
  color: var(--lib-brand);
  display: flex;
  flex: none;
  font-size: 44px;
  font-weight: 700;
  height: 210px;
  justify-content: center;
  overflow: hidden;
  width: 150px;
}

.detail__cover img {
  height: 100%;
  object-fit: cover;
  width: 100%;
}

.detail__info {
  flex: 1;
  min-width: 0;
}

.detail__title {
  font-size: 20px;
  margin: 0 0 14px;
}

.detail__actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

.group-title {
  align-items: center;
  display: inline-flex;
  gap: 8px;
  font-weight: 600;
}

.reserve-book {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 14px;
}

.reserve-select {
  width: 100%;
}
</style>
