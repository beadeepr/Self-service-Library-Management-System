<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="门禁通行"
    stage="阶段 6 · 物联侧页面"
    :apis="['POST /api/v1/visits/access/', 'GET /api/v1/branches/{id}/occupancy/', 'POST /api/v1/visits/help/']"
    note="依赖刘经纬的接口。入馆校验信用、冻结状态与人数上限；出馆不受欠费限制。门禁读卡为幂等操作，需带 Idempotency-Key。"
  />
</template>
