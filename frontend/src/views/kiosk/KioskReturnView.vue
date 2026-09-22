<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="自助还书"
    stage="阶段 3 · Kiosk 借还"
    :apis="['GET /api/v1/loans/?copy=&returned_at__isnull=true', 'POST /api/v1/loans/{id}/return/']"
    note="按副本查出在借记录后归还，支持跨馆归还与损坏标记；归还需带 Idempotency-Key。归还后进入待处理，需消毒上架才可外借。"
  />
</template>
