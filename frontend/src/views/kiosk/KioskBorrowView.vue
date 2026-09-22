<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="自助借书"
    stage="阶段 3 · Kiosk 借还"
    :apis="['GET /api/v1/copies/?rfid=', 'POST /api/v1/loans/borrow/', 'GET /api/v1/rules/current/']"
    note="三步流程：识别副本 → 确认借阅 → 打印凭条。借书只接受 copy（物理副本 ID），需由 RFID 或馆藏号解析出可借副本；必须带 Idempotency-Key。"
  />
</template>
