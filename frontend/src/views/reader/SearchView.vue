<script setup lang="ts">
/**
 * 图书检索，对应 FR-07~FR-09。
 *
 * 检索条件与页码都放在 URL 查询参数里，由路由查询驱动请求：
 * 这样刷新、前进后退、把结果链接发给别人都能复现同一页结果。
 * 后端每页固定 20 条且不支持 page_size，因此分页直接沿用后端的 count。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { searchBooks, type Book } from '@/api/books'
import { errorMessage } from '@/api/client'
import { useCatalog } from '@/composables/useCatalog'
import BookCard from '@/components/BookCard.vue'

const route = useRoute()
const router = useRouter()
// 解构出来：只有 setup 顶层的 ref 才会在模板里自动解包，挂在对象上访问会拿到 ref 本身。
const { categories, ensureLoaded, categoryName } = useCatalog()

const PAGE_SIZE = 20

const books = ref<Book[]>([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')

const orderingOptions = [
  { value: '', label: '默认排序' },
  { value: 'title', label: '书名升序' },
  { value: '-title', label: '书名降序' },
  { value: 'price', label: '价格从低到高' },
  { value: '-price', label: '价格从高到低' },
  { value: '-id', label: '最新入库' },
]

/** 查询参数可能是数组或 null，统一取首个字符串。 */
function query(name: string): string {
  const value = route.query[name]
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : ''
  return typeof value === 'string' ? value : ''
}

const current = computed(() => ({
  search: query('search'),
  category: query('category'),
  ordering: query('ordering'),
  page: Math.max(1, Number(query('page')) || 1),
}))

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await searchBooks({
      search: current.value.search,
      category: current.value.category,
      ordering: current.value.ordering,
      page: current.value.page,
    })
    books.value = data.results
    total.value = data.count
  } catch (error) {
    books.value = []
    total.value = 0
    ElMessage.error(errorMessage(error, '检索失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => void ensureLoaded().catch(() => undefined))

watch(
  () => route.query,
  () => {
    keyword.value = current.value.search
    void load()
  },
  { immediate: true },
)

/** 改动任一筛选条件都要回到第 1 页，否则会停在已越界的页码上。 */
function replaceQuery(next: Record<string, string>): void {
  const merged: Record<string, string> = {
    search: current.value.search,
    category: current.value.category,
    ordering: current.value.ordering,
    ...next,
  }
  const cleaned = Object.fromEntries(Object.entries(merged).filter(([, value]) => value !== ''))
  void router.replace({ name: 'reader-search', query: cleaned })
}

function submitSearch(): void {
  replaceQuery({ search: keyword.value.trim(), page: '' })
}

function resetFilters(): void {
  keyword.value = ''
  void router.replace({ name: 'reader-search' })
}

function changePage(page: number): void {
  replaceQuery({ page: String(page) })
}

function changeCategory(value: string | undefined): void {
  replaceQuery({ category: value ?? '', page: '' })
}

function changeOrdering(value: string | undefined): void {
  replaceQuery({ ordering: value ?? '', page: '' })
}

const hasFilter = computed(() => !!(current.value.search || current.value.category || current.value.ordering))
</script>

<template>
  <div>
    <el-card shadow="never" class="search-bar">
      <div class="search-bar__row">
        <el-input
          v-model="keyword"
          clearable
          placeholder="书名、作者、ISBN、分类号或索书号"
          @keyup.enter="submitSearch"
          @clear="submitSearch"
        />
        <el-select
          :model-value="current.category"
          placeholder="全部分类"
          clearable
          class="search-bar__select"
          @update:model-value="changeCategory"
        >
          <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="String(item.id)" />
        </el-select>
        <el-select
          :model-value="current.ordering"
          class="search-bar__select"
          @update:model-value="changeOrdering"
        >
          <el-option v-for="item in orderingOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-button type="primary" @click="submitSearch">检索</el-button>
        <el-button v-if="hasFilter" @click="resetFilters">重置</el-button>
      </div>
    </el-card>

    <div class="result-head">
      <span>共 {{ total }} 条结果</span>
      <span v-if="current.search" class="lib-text-muted">关键词「{{ current.search }}」</span>
    </div>

    <div v-loading="loading" class="book-grid">
      <BookCard
        v-for="book in books"
        :key="book.id"
        :book="book"
        :category-name="categoryName(book.category)"
      />
    </div>

    <el-empty v-if="!loading && !books.length" description="没有匹配的图书，换个关键词试试" />

    <el-pagination
      v-if="total > PAGE_SIZE"
      class="pager"
      layout="prev, pager, next, total"
      :total="total"
      :page-size="PAGE_SIZE"
      :current-page="current.page"
      @current-change="changePage"
    />
  </div>
</template>

<style scoped>
.search-bar {
  margin-bottom: 16px;
}

.search-bar__row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.search-bar__row :deep(.el-input) {
  flex: 1;
  min-width: 220px;
}

.search-bar__select {
  width: 150px;
}

.result-head {
  color: var(--lib-text-muted);
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.book-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  min-height: 80px;
}

.pager {
  justify-content: center;
  margin-top: 20px;
}
</style>
