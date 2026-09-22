<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="首页"
    stage="阶段 2 · 读者 Web 主线"
    :apis="['GET /api/v1/announcements/', 'GET /api/v1/activities/', 'GET /api/v1/notifications/']"
    note="公告与活动为公开只读；站内通知需登录，展示预约到馆、到期、逾期提醒。"
  />
</template>
