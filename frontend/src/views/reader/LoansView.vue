<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="我的借阅"
    stage="阶段 3 · Kiosk 借还"
    :apis="[
      'GET /api/v1/loans/?returned_at__isnull=true',
      'POST /api/v1/loans/{id}/renew/',
      'GET /api/v1/rules/current/',
    ]"
    note="区分在借/历史/逾期三个视图；续借需带 Idempotency-Key，且受逾期、预约队列、续借次数与欠费校验限制。"
  />
</template>
