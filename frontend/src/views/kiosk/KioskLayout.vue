<script setup lang="ts">
/**
 * 自助终端外壳：全屏、大字号、少文字，适合触摸屏。
 * 终端在读者刷卡签到后以读者身份操作，因此这里只做框架，身份由各功能页自行确认。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useReaderStore } from '@/stores/reader'
import '@/styles/kiosk.css'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const reader = useReaderStore()

const title = computed(() => route.meta.title ?? '自助终端')

async function handleExit(): Promise<void> {
  await auth.logout()
  reader.reset()
  await router.replace({ name: 'kiosk-home' })
}
</script>

<template>
  <div class="kiosk-shell">
    <header class="kiosk-shell__bar">
      <button class="kiosk-btn kiosk-btn--ghost" type="button" @click="router.back()">返回</button>
      <h1 class="kiosk-shell__title">{{ title }}</h1>
      <div class="kiosk-shell__right">
        <span v-if="auth.isAuthenticated" class="kiosk-shell__who">{{ reader.displayName }}</span>
        <button v-if="auth.isAuthenticated" class="kiosk-btn kiosk-btn--ghost" type="button" @click="handleExit">
          结束使用
        </button>
      </div>
    </header>

    <main class="kiosk-shell__body">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.kiosk-shell {
  background: var(--kiosk-bg);
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.kiosk-shell__bar {
  align-items: center;
  background: var(--kiosk-surface);
  border-bottom: 2px solid var(--kiosk-border);
  display: grid;
  gap: 16px;
  grid-template-columns: 1fr auto 1fr;
  padding: 14px 24px;
}

.kiosk-shell__title {
  font-size: var(--kiosk-title);
  font-weight: 700;
  margin: 0;
  text-align: center;
}

.kiosk-shell__right {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: flex-end;
}

.kiosk-shell__who {
  font-size: var(--kiosk-text);
  font-weight: 600;
}

.kiosk-shell__body {
  flex: 1;
  margin: 0 auto;
  max-width: 1000px;
  padding: 28px 24px 48px;
  width: 100%;
}
</style>
