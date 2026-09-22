/**
 * 路由表与访问守卫。
 *
 * 三端同源不同前缀：`/reader` 读者 Web、`/kiosk` 自助终端、`/admin` 管理后台。
 * 权限以后端为准（后端对每个接口都做了角色校验），这里的守卫只负责把用户导到能用的一端，
 * 不作为安全边界 —— 前端隐藏入口不等于接口被保护。
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/api/session'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** 需要登录 */
    requiresAuth?: boolean
    /** 仅未登录可见（登录、注册页），已登录会被送回各自首页 */
    guestOnly?: boolean
    /** 允许的角色；未列出的角色会被送回自己那一端 */
    roles?: Role[]
  }
}

const readerRoutes: RouteRecordRaw = {
  path: '/reader',
  component: () => import('@/views/reader/ReaderLayout.vue'),
  children: [
    { path: '', redirect: { name: 'reader-home' } },
    { path: 'home', name: 'reader-home', component: () => import('@/views/reader/HomeView.vue'), meta: { title: '首页' } },
    { path: 'search', name: 'reader-search', component: () => import('@/views/reader/SearchView.vue'), meta: { title: '图书检索' } },
    {
      path: 'books/:id',
      name: 'reader-book-detail',
      component: () => import('@/views/reader/BookDetailView.vue'),
      meta: { title: '图书详情' },
    },
    { path: 'login', name: 'reader-login', component: () => import('@/views/reader/LoginView.vue'), meta: { title: '登录', guestOnly: true } },
    { path: 'register', name: 'reader-register', component: () => import('@/views/reader/RegisterView.vue'), meta: { title: '注册', guestOnly: true } },
    {
      path: 'loans',
      name: 'reader-loans',
      component: () => import('@/views/reader/LoansView.vue'),
      meta: { title: '我的借阅', requiresAuth: true },
    },
    {
      path: 'reservations',
      name: 'reader-reservations',
      component: () => import('@/views/reader/ReservationsView.vue'),
      meta: { title: '我的预约', requiresAuth: true },
    },
    {
      path: 'fines',
      name: 'reader-fines',
      component: () => import('@/views/reader/FinesView.vue'),
      meta: { title: '罚款与押金', requiresAuth: true },
    },
    {
      path: 'profile',
      name: 'reader-profile',
      component: () => import('@/views/reader/ProfileView.vue'),
      meta: { title: '个人中心', requiresAuth: true },
    },
  ],
}

const kioskRoutes: RouteRecordRaw = {
  path: '/kiosk',
  component: () => import('@/views/kiosk/KioskLayout.vue'),
  children: [
    { path: '', name: 'kiosk-home', component: () => import('@/views/kiosk/KioskHomeView.vue'), meta: { title: '自助终端' } },
    {
      path: 'borrow',
      name: 'kiosk-borrow',
      component: () => import('@/views/kiosk/KioskBorrowView.vue'),
      meta: { title: '自助借书', requiresAuth: true },
    },
    {
      path: 'return',
      name: 'kiosk-return',
      component: () => import('@/views/kiosk/KioskReturnView.vue'),
      meta: { title: '自助还书', requiresAuth: true },
    },
    {
      path: 'access',
      name: 'kiosk-access',
      component: () => import('@/views/kiosk/KioskAccessView.vue'),
      meta: { title: '门禁通行', requiresAuth: true },
    },
  ],
}

const adminRoutes: RouteRecordRaw = {
  path: '/admin',
  component: () => import('@/views/admin/AdminLayout.vue'),
  meta: { requiresAuth: true, roles: ['admin', 'operator'] },
  children: [
    { path: '', redirect: { name: 'admin-dashboard' } },
    {
      path: 'dashboard',
      name: 'admin-dashboard',
      component: () => import('@/views/admin/DashboardView.vue'),
      meta: { title: '运营大屏' },
    },
    { path: 'books', name: 'admin-books', component: () => import('@/views/admin/BooksManageView.vue'), meta: { title: '图书与馆藏' } },
    {
      path: 'readers',
      name: 'admin-readers',
      component: () => import('@/views/admin/ReadersManageView.vue'),
      // 后端 readers/ 为 AdminOnly，运维访问会 403，故此处也限制为管理员。
      meta: { title: '读者管理', roles: ['admin'] },
    },
    { path: 'loans', name: 'admin-loans', component: () => import('@/views/admin/LoansManageView.vue'), meta: { title: '借还管理' } },
    { path: 'devices', name: 'admin-devices', component: () => import('@/views/admin/DevicesView.vue'), meta: { title: '设备状态' } },
    { path: 'alerts', name: 'admin-alerts', component: () => import('@/views/admin/AlertsView.vue'), meta: { title: '告警中心' } },
  ],
}

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: { name: 'reader-home' } },
  // /login 作为读者登录页的别名，便于过期的会话统一跳转。
  { path: '/login', redirect: { name: 'reader-login' } },
  readerRoutes,
  kioskRoutes,
  adminRoutes,
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/errors/NotFoundView.vue'), meta: { title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth)
  // 取最深一层声明了 roles 的记录：子路由（如 /admin/readers）可以比父路由更严格。
  const requiredRoles = to.matched.reduce<Role[] | undefined>((acc, record) => record.meta.roles ?? acc, undefined)

  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { path: auth.homePath(), replace: true }
  }

  if (requiresAuth && !auth.isAuthenticated) {
    const redirect = to.fullPath === '/' ? undefined : to.fullPath
    return { name: 'reader-login', query: redirect ? { redirect } : {}, replace: true }
  }

  if (requiredRoles && !auth.hasRole(...requiredRoles)) {
    return { path: auth.homePath(), replace: true }
  }

  return true
})

router.afterEach((to) => {
  const title = to.meta.title
  document.title = title ? `${title} · 无人值守图书馆系统` : '无人值守图书馆系统'
})

export default router
