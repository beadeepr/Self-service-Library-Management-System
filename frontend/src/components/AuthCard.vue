<script setup lang="ts">
/** 登录/注册页共用的居中卡片外壳。 */
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<template>
  <div class="auth-wrap">
    <el-card class="auth-card" shadow="never">
      <h1 class="auth-card__title">{{ title }}</h1>
      <p v-if="subtitle" class="auth-card__subtitle">{{ subtitle }}</p>
      <slot />
    </el-card>
  </div>
</template>

<style scoped>
.auth-wrap {
  align-items: center;
  display: flex;
  justify-content: center;
  min-height: calc(100vh - var(--lib-header-height) - 60px);
}

.auth-card {
  border-radius: var(--lib-radius);
  box-shadow: var(--lib-shadow);
  width: 100%;
  max-width: 420px;
}

.auth-card__title {
  font-size: 20px;
  margin: 0 0 4px;
  text-align: center;
}

.auth-card__subtitle {
  color: var(--lib-text-muted);
  margin: 0 0 20px;
  text-align: center;
}
</style>
