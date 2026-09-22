<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="告警中心"
    stage="阶段 6 · 物联侧页面"
    :apis="['GET /api/v1/alerts/', 'POST /api/v1/alerts/{id}/transition/', 'GET /api/v1/work-orders/']"
    note="依赖刘经纬的接口。按级别展示告警并做 open → acknowledged → resolved 流转，关闭时必须填写处理结论。"
  />
</template>
