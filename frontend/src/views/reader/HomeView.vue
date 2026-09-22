<script setup lang="ts">
/**
 * 读者首页：检索入口 + 公告 + 活动 + 站内通知。
 *
 * 公告与活动是公开只读接口，未登录也会加载；
 * 站内通知只返回本人数据，必须登录后请求，因此未登录时不发这个请求。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listActivities, listAnnouncements, listNotifications, markNotificationRead, type Activity, type Announcement, type Notification } from '@/api/content'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useCatalog } from '@/composables/useCatalog'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()
const { branchName, ensureLoaded } = useCatalog()

const announcements = ref<Announcement[]>([])
const activities = ref<Activity[]>([])
const notifications = ref<Notification[]>([])
const loading = ref(false)
const keyword = ref('')

const unreadCount = computed(() => notifications.value.filter((item) => !item.read_at).length)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [announcementPage, activityPage] = await Promise.all([listAnnouncements(), listActivities()])
    announcements.value = announcementPage.results
    activities.value = activityPage.results
    // 未登录时该接口会 401，直接跳过而不是让整页报错。
    notifications.value = auth.isAuthenticated ? (await listNotifications()).results : []
  } catch (error) {
    ElMessage.error(errorMessage(error, '首页内容加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void ensureLoaded().catch(() => undefined)
  void load()
})

function submitSearch(): void {
  const search = keyword.value.trim()
  void router.push({ name: 'reader-search', query: search ? { search } : {} })
}

async function readNotification(item: Notification): Promise<void> {
  if (item.read_at) return
  try {
    const updated = await markNotificationRead(item.id)
    item.read_at = updated.read_at
  } catch (error) {
    ElMessage.error(errorMessage(error, '标记已读失败'))
  }
}
</script>

<template>
  <div class="lib-stack">
    <el-card shadow="never" class="hero">
      <h2 class="hero__title">找一本想看的书</h2>
      <p class="hero__hint lib-text-muted">支持书名、作者、ISBN、分类号与索书号检索</p>
      <div class="hero__search">
        <el-input v-model="keyword" size="large" clearable placeholder="输入关键词" @keyup.enter="submitSearch" />
        <el-button type="primary" size="large" @click="submitSearch">检索</el-button>
      </div>
    </el-card>

    <el-card v-if="auth.isAuthenticated" shadow="never">
      <template #header>
        <div class="card-head">
          <span>我的通知</span>
          <el-tag v-if="unreadCount" type="danger" size="small" effect="plain">{{ unreadCount }} 条未读</el-tag>
        </div>
      </template>

      <el-empty v-if="!notifications.length" description="暂无通知" :image-size="70" />
      <ul v-else class="notice-list">
        <li v-for="item in notifications" :key="item.id" class="notice-list__item" :class="{ 'is-unread': !item.read_at }">
          <div class="notice-list__head">
            <span class="notice-list__title">{{ item.title }}</span>
            <span class="lib-text-muted">{{ formatDateTime(item.created_at) }}</span>
          </div>
          <p class="notice-list__body">{{ item.body }}</p>
          <el-button v-if="!item.read_at" text type="primary" size="small" @click="readNotification(item)">标记已读</el-button>
        </li>
      </ul>
    </el-card>

    <el-card shadow="never">
      <template #header>公告</template>
      <el-empty v-if="!announcements.length" description="暂无公告" :image-size="70" />
      <ul v-else class="notice-list">
        <li v-for="item in announcements" :key="item.id" class="notice-list__item">
          <div class="notice-list__head">
            <span class="notice-list__title">{{ item.title }}</span>
            <span class="lib-text-muted">{{ formatDateTime(item.created_at) }}</span>
          </div>
          <p class="notice-list__body">{{ item.body }}</p>
        </li>
      </ul>
    </el-card>

    <el-card shadow="never">
      <template #header>近期活动</template>
      <el-empty v-if="!activities.length" description="暂无活动" :image-size="70" />
      <ul v-else class="notice-list">
        <li v-for="item in activities" :key="item.id" class="notice-list__item">
          <div class="notice-list__head">
            <span class="notice-list__title">{{ item.title }}</span>
            <span class="lib-text-muted">{{ formatDateTime(item.starts_at) }}</span>
          </div>
          <p class="notice-list__body lib-text-muted">
            {{ branchName(item.branch) }} · 面向{{ item.audience || '全体读者' }} · 名额 {{ item.capacity }}
          </p>
        </li>
      </ul>
    </el-card>

    <p v-if="loading" class="lib-text-muted">加载中…</p>
  </div>
</template>

<style scoped>
.hero__title {
  font-size: 20px;
  margin: 0 0 4px;
}

.hero__hint {
  margin: 0 0 16px;
}

.hero__search {
  display: flex;
  gap: 10px;
  max-width: 620px;
}

.card-head {
  align-items: center;
  display: flex;
  gap: 8px;
}

.notice-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.notice-list__item {
  border-bottom: 1px solid var(--lib-border);
  padding: 12px 0;
}

.notice-list__item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.notice-list__item.is-unread .notice-list__title::before {
  background: #f56c6c;
  border-radius: 50%;
  content: '';
  display: inline-block;
  height: 6px;
  margin-right: 6px;
  vertical-align: middle;
  width: 6px;
}

.notice-list__head {
  align-items: baseline;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.notice-list__title {
  font-weight: 600;
}

.notice-list__body {
  margin: 4px 0 0;
  white-space: pre-wrap;
}
</style>
