/**
 * 分类与网点这类低频变更的对照数据，多个页面共用。
 *
 * 用模块级状态缓存，避免每个页面各拉一次；并发调用共享同一个 Promise，
 * 不会重复发请求。数据本身由管理员在后台维护，读者端只读。
 */
import { ref } from 'vue'
import { getAll } from '@/api/client'
import { listBranches, listCategories, type Branch, type Category } from '@/api/books'

const categories = ref<Category[]>([])
const branches = ref<Branch[]>([])
let loading: Promise<void> | null = null

async function load(): Promise<void> {
  const [nextCategories, nextBranches] = await Promise.all([
    getAll<Category>('/categories/'),
    getAll<Branch>('/branches/'),
  ])
  categories.value = nextCategories
  branches.value = nextBranches
}

export function useCatalog() {
  /** 首次调用时拉取，之后复用缓存；force=true 用于后台改完数据后刷新。 */
  async function ensureLoaded(force = false): Promise<void> {
    if (force) {
      loading = null
      categories.value = []
      branches.value = []
    } else if (categories.value.length && branches.value.length) {
      return
    }
    if (!loading) {
      loading = load().catch((error) => {
        // 失败后清掉，让下次调用可以重试，而不是永久缓存一个被拒的 Promise。
        loading = null
        throw error
      })
    }
    return loading
  }

  function categoryName(id: number | null | undefined): string {
    if (id === null || id === undefined) return '未分类'
    return categories.value.find((item) => item.id === id)?.name ?? `分类 ${id}`
  }

  function branchName(id: number | null | undefined): string {
    if (id === null || id === undefined) return '未知网点'
    return branches.value.find((item) => item.id === id)?.name ?? `网点 ${id}`
  }

  return { categories, branches, ensureLoaded, categoryName, branchName }
}

export { listCategories, listBranches }
