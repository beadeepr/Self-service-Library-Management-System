<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="运营大屏"
    stage="阶段 6 · 物联侧页面"
    :apis="['GET /api/v1/reports/summary/', 'GET /api/v1/branches/{id}/occupancy/', 'GET /api/v1/reports/export/']"
    note="依赖刘经纬的接口。馆藏/借阅趋势/热门图书/客流/收入/工时成本汇总；在馆人数与空闲座位为人数估算，未连接座位传感器。仅管理员与运维可读。"
  />
</template>
