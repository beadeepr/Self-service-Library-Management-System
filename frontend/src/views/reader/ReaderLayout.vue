<script setup lang="ts">
/** 读者端外壳：顶部导航 + 登录态入口。读者侧的公共查询无需登录即可使用。 */
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const reader = useReaderStore()

const navItems = [
  { name: 'reader-home', label: '首页' },
  { name: 'reader-search', label: '图书检索' },
  { name: 'reader-loans', label: '我的借阅' },
  { name: 'reader-reservations', label: '我的预约' },
  { name: 'reader-fines', label: '罚款与押金' },
  { name: 'reader-profile', label: '个人中心' },
]

const activeName = computed(() => (typeof route.name === 'string' ? route.name : ''))

// 登录后拉取资料（信用、押金、实名状态），供页头与个人中心复用。
watch(
  () => auth.isAuthenticated,
  (loggedIn) => {
    if (loggedIn) void reader.load()
    else reader.reset()
  },
  { immediate: true },
)

async function handleLogout(): Promise<void> {
  await auth.logout()
  reader.reset()
  ElMessage.success('已退出登录')
  await router.push({ name: 'reader-login' })
}
</script>

<template>
  <div class="reader-layout">
    <header class="reader-header">
      <RouterLink class="reader-header__brand" :to="{ name: 'reader-home' }">无人值守图书馆</RouterLink>

      <el-menu class="reader-header__nav" mode="horizontal" :default-active="activeName" :ellipsis="false" router>
        <el-menu-item v-for="item in navItems" :key="item.name" :index="item.name" :route="{ name: item.name }">
          {{ item.label }}
        </el-menu-item>
      </el-menu>

      <div class="reader-header__account">
        <el-button text @click="router.push({ name: 'kiosk-home' })">自助终端</el-button>

        <el-dropdown v-if="auth.isAuthenticated">
          <span class="reader-header__user">
            {{ reader.displayName }}
            <el-tag v-if="reader.creditLevel !== 'normal'" type="warning" size="small" effect="plain">
              {{ reader.creditLevel === 'untrusted' ? '失信' : '受限' }}
            </el-tag>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="router.push({ name: 'reader-profile' })">个人中心</el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <template v-else>
          <el-button type="primary" @click="router.push({ name: 'reader-login' })">登录</el-button>
          <el-button @click="router.push({ name: 'reader-register' })">注册</el-button>
        </template>
      </div>
    </header>

    <main class="lib-page">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.reader-layout {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.reader-header {
  align-items: center;
  background: var(--lib-surface);
  border-bottom: 1px solid var(--lib-border);
  display: flex;
  gap: 16px;
  height: var(--lib-header-height);
  padding: 0 20px;
}

.reader-header__brand {
  color: var(--lib-brand);
  flex: none;
  font-size: 17px;
  font-weight: 700;
}

.reader-header__nav {
  border-bottom: none;
  flex: 1;
  min-width: 0;
}

.reader-header__account {
  align-items: center;
  display: flex;
  flex: none;
  gap: 8px;
}

.reader-header__user {
  align-items: center;
  cursor: pointer;
  display: inline-flex;
  gap: 6px;
  outline: none;
}
</style>
