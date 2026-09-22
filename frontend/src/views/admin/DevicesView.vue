<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="设备状态"
    stage="阶段 6 · 物联侧页面"
    :apis="[
      'GET /api/v1/devices/',
      'GET /api/v1/device-events/',
      'GET /api/v1/device-commands/',
      'POST /api/v1/devices/{id}/command/',
    ]"
    note="依赖刘经纬的接口。设备台账只读展示在线状态与设备影子；远程指令状态为 pending 时仅代表已登记，不代表硬件已执行。"
  />
</template>
