<script setup lang="ts">
/** 管理后台外壳：左侧菜单按角色过滤，右侧内容区。 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/api/session'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

interface AdminMenuItem {
  name: string
  label: string
  /** 未声明表示管理员与运维都可见 */
  roles?: Role[]
}

const allItems: AdminMenuItem[] = [
  { name: 'admin-dashboard', label: '运营大屏' },
  { name: 'admin-books', label: '图书与馆藏' },
  { name: 'admin-readers', label: '读者管理', roles: ['admin'] },
  // 后端对非管理员只返回本人借阅，且催还/代办借还均为 AdminOnly，故仅对管理员展示。
  { name: 'admin-loans', label: '借还管理', roles: ['admin'] },
  { name: 'admin-devices', label: '设备状态' },
  { name: 'admin-alerts', label: '告警中心' },
]

// 后端 readers/ 仅管理员可读，运维账号不展示该入口。
const menuItems = computed(() => allItems.filter((item) => !item.roles || auth.hasRole(...item.roles)))
const activeName = computed(() => (typeof route.name === 'string' ? route.name : ''))

const roleLabel = computed(() => (auth.isAdmin ? '管理员' : auth.isOperator ? '运维' : '读者'))

async function handleLogout(): Promise<void> {
  await auth.logout()
  ElMessage.success('已退出登录')
  await router.push({ name: 'reader-login' })
}
</script>

<template>
  <el-container class="admin-layout">
    <el-aside width="210px" class="admin-aside">
      <div class="admin-aside__brand">图书馆管理后台</div>
      <el-menu :default-active="activeName" router>
        <el-menu-item v-for="item in menuItems" :key="item.name" :index="item.name" :route="{ name: item.name }">
          {{ item.label }}
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="admin-header">
        <span class="admin-header__who">{{ roleLabel }}</span>
        <div class="admin-header__actions">
          <el-button text @click="router.push({ name: 'reader-home' })">读者端</el-button>
          <el-button text @click="router.push({ name: 'kiosk-home' })">自助终端</el-button>
          <el-button text type="danger" @click="handleLogout">退出</el-button>
        </div>
      </el-header>

      <el-main class="admin-main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout {
  min-height: 100%;
}

.admin-aside {
  background: var(--lib-surface);
  border-right: 1px solid var(--lib-border);
}

.admin-aside__brand {
  color: var(--lib-brand);
  font-size: 16px;
  font-weight: 700;
  padding: 18px 20px;
}

.admin-header {
  align-items: center;
  background: var(--lib-surface);
  border-bottom: 1px solid var(--lib-border);
  display: flex;
  justify-content: space-between;
}

.admin-header__who {
  font-weight: 600;
}

.admin-header__actions {
  display: flex;
  gap: 4px;
}

.admin-main {
  background: var(--lib-bg);
}
</style>
