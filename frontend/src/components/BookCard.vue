<script setup lang="ts">
/** 书目卡片。可借状态直接取自后端统计的 available_count，不在前端重算。 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { Book } from '@/api/books'
import { formatMoney } from '@/utils/format'

const props = defineProps<{
  book: Book
  categoryName?: string
}>()

const router = useRouter()

const availability = computed(() => {
  if (!props.book.active) return { type: 'info' as const, text: '已下架' }
  if (props.book.available_count > 0) return { type: 'success' as const, text: `可借 ${props.book.available_count} 册` }
  return { type: 'warning' as const, text: '暂无可借' }
})

function openDetail(): void {
  void router.push({ name: 'reader-book-detail', params: { id: props.book.id } })
}
</script>

<template>
  <el-card class="book-card" shadow="hover" @click="openDetail">
    <div class="book-card__body">
      <div class="book-card__cover">
        <img v-if="book.cover" :src="book.cover" :alt="book.title" />
        <span v-else class="book-card__cover-text">{{ book.title.slice(0, 1) }}</span>
      </div>

      <div class="book-card__info">
        <h3 class="book-card__title" :title="book.title">{{ book.title }}</h3>
        <p class="book-card__meta">{{ book.author || '佚名' }}</p>
        <p class="book-card__meta">{{ book.publisher || '出版社未录入' }}</p>
        <p class="book-card__meta">
          <span v-if="categoryName">{{ categoryName }}</span>
          <span v-if="book.call_number"> · 索书号 {{ book.call_number }}</span>
        </p>
        <div class="book-card__foot">
          <el-tag :type="availability.type" size="small" effect="plain">{{ availability.text }}</el-tag>
          <span class="book-card__price">{{ formatMoney(book.price) }}</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.book-card {
  cursor: pointer;
  height: 100%;
}

.book-card__body {
  display: flex;
  gap: 12px;
}

.book-card__cover {
  align-items: center;
  background: var(--lib-brand-soft);
  border-radius: 6px;
  color: var(--lib-brand);
  display: flex;
  flex: none;
  font-size: 26px;
  font-weight: 700;
  height: 104px;
  justify-content: center;
  overflow: hidden;
  width: 76px;
}

.book-card__cover img {
  height: 100%;
  object-fit: cover;
  width: 100%;
}

.book-card__info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.book-card__title {
  font-size: 15px;
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.book-card__meta {
  color: var(--lib-text-muted);
  font-size: 12px;
  margin: 0 0 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.book-card__foot {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 8px;
}

.book-card__price {
  color: var(--lib-text-muted);
  font-size: 12px;
}
</style>
