<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="图书详情"
    stage="阶段 2 · 读者 Web 主线"
    :apis="['GET /api/v1/books/{id}/', 'GET /api/v1/copies/?book=&status=available', 'POST /api/v1/reservations/']"
    note="展示书目信息与各馆可借副本位置；无可借副本时提供预约入口（预约需带 Idempotency-Key）。"
  />
</template>
