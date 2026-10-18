/**
 * 对照数据缓存：分类、网点、副本。
 *
 * 三者在多个页面反复使用（检索、详情、借还、后台），用模块级状态缓存避免重复请求；
 * 并发调用共享同一个 Promise。数据由管理员在后台维护，读者端只读。
 *
 * 书目与副本也是全量拉取的：借阅记录只带 copy 外键，要把「在借」显示成书名，
 * 必须自己把 loan.copy → copy.book → book.title 串起来。后端既没有展开 copy.book，
 * 也没有 id__in 过滤，所以这里一次取全并在内存里查。
 * 馆藏上万条时应改为后端展开字段，而不是继续全量拉取。
 */
import { ref } from 'vue'
import { getAll } from '@/api/client'
import { listBranches, listCategories, type Book, type Branch, type Category, type Copy } from '@/api/books'

const categories = ref<Category[]>([])
const branches = ref<Branch[]>([])
const copies = ref<Copy[]>([])
const books = ref<Book[]>([])
let loading: Promise<void> | null = null

async function load(): Promise<void> {
  const [nextCategories, nextBranches, nextCopies, nextBooks] = await Promise.all([
    getAll<Category>('/categories/'),
    getAll<Branch>('/branches/'),
    getAll<Copy>('/copies/'),
    getAll<Book>('/books/'),
  ])
  categories.value = nextCategories
  branches.value = nextBranches
  copies.value = nextCopies
  books.value = nextBooks
}

export function useCatalog() {
  /**
   * 首次调用时拉取，之后复用缓存；force=true 用于借还、消毒上架等改变副本状态后刷新。
   * 强制刷新时不清空现有数据，只在新数据到达后整体替换 —— 否则界面上会短暂闪成空值。
   */
  async function ensureLoaded(force = false): Promise<void> {
    if (!force && categories.value.length && branches.value.length && copies.value.length && books.value.length) {
      return
    }
    if (force) loading = null
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

  function copyOf(copyId: number | null | undefined): Copy | undefined {
    if (copyId === null || copyId === undefined) return undefined
    return copies.value.find((item) => item.id === copyId)
  }

  function copyByRfid(rfid: string): Copy | undefined {
    const target = rfid.trim().toLowerCase()
    return copies.value.find((item) => item.rfid.toLowerCase() === target)
  }

  function bookIdOfCopy(copyId: number | null | undefined): number | null {
    return copyOf(copyId)?.book ?? null
  }

  function bookOf(id: number | null | undefined): Book | undefined {
    if (id === null || id === undefined) return undefined
    return books.value.find((item) => item.id === id)
  }

  /** 借阅记录 → 书目：loan.copy → copy.book → book。 */
  function bookOfLoanCopy(copyId: number | null | undefined): Book | undefined {
    return bookOf(bookIdOfCopy(copyId))
  }

  /** 某书目当前可借的副本。 */
  function availableCopiesOfBook(bookId: number): Copy[] {
    return copies.value.filter((item) => item.book === bookId && item.status === 'available')
  }

  return {
    categories,
    branches,
    copies,
    books,
    ensureLoaded,
    categoryName,
    branchName,
    copyOf,
    copyByRfid,
    bookIdOfCopy,
    bookOf,
    bookOfLoanCopy,
    availableCopiesOfBook,
  }
}

export { listCategories, listBranches }
