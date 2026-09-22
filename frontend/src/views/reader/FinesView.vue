<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="罚款与押金"
    stage="阶段 5 · 读者 P1"
    :apis="[
      'GET /api/v1/fines/',
      'POST /api/v1/payments/',
      'POST /api/v1/payments/{id}/simulate/',
      'GET /api/v1/deposit-entries/',
    ]"
    note="逾期每天 0.50 元，不足一天按一天。支付为模拟通道，重复调用不重复入账。"
  />
</template>
