<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="图书与馆藏"
    stage="阶段 4 · 管理后台"
    :apis="[
      'GET/POST/PATCH /api/v1/books/',
      'POST /api/v1/books/{id}/intake/',
      'GET /api/v1/copies/',
      'POST /api/v1/copies/{id}/set-status/',
      'POST /api/v1/copies/{id}/disinfect/',
      'POST /api/v1/copies/{id}/shelve/',
    ]"
    note="书目（Book）与副本（Copy）分开维护，库存由副本数量统计。入库扫码生成唯一 RFID；消毒上架后转可借并自动分配下一位预约者。"
  />
</template>
