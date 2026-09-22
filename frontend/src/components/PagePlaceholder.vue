<script setup lang="ts">
/**
 * 尚未实现的页面占位。列出该页依赖的后端接口与计划阶段，
 * 让骨架阶段的每一次导航都能说明「这里将来是什么、依赖谁」。
 */
defineProps<{
  title: string
  stage: string
  apis?: string[]
  note?: string
}>()
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="placeholder__head">
        <span class="placeholder__title">{{ title }}</span>
        <el-tag type="info" size="small" effect="plain">{{ stage }}</el-tag>
      </div>
    </template>

    <el-empty description="页面骨架已就绪，业务实现见下方阶段" :image-size="80" />

    <div v-if="apis && apis.length" class="placeholder__block">
      <p class="placeholder__label">依赖后端接口</p>
      <ul class="placeholder__list">
        <li v-for="api in apis" :key="api">
          <code>{{ api }}</code>
        </li>
      </ul>
    </div>

    <p v-if="note" class="placeholder__note">{{ note }}</p>
  </el-card>
</template>

<style scoped>
.placeholder__head {
  align-items: center;
  display: flex;
  gap: 8px;
}

.placeholder__title {
  font-size: 16px;
  font-weight: 600;
}

.placeholder__block {
  border-top: 1px solid var(--lib-border);
  padding-top: 12px;
}

.placeholder__label {
  color: var(--lib-text-muted);
  margin: 0 0 6px;
}

.placeholder__list {
  color: var(--lib-text-muted);
  margin: 0;
  padding-left: 20px;
}

.placeholder__note {
  color: var(--lib-text-muted);
  margin: 12px 0 0;
}
</style>
