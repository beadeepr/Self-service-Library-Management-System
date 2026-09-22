<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="我的预约"
    stage="阶段 5 · 读者 P1"
    :apis="['GET /api/v1/reservations/', 'POST /api/v1/reservations/{id}/cancel/', 'POST /api/v1/reservations/{id}/collect/']"
    note="到馆保留默认 2 天，超时自动释放；取书生成借阅记录。取消与取书均需幂等键。"
  />
</template>
