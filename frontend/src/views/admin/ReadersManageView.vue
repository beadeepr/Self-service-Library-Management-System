<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="读者管理"
    stage="阶段 4 · 管理后台"
    :apis="[
      'GET /api/v1/readers/',
      'POST /api/v1/readers/{id}/manage/',
      'GET /api/v1/credit-entries/',
      'GET /api/v1/deposit-entries/',
      'GET /api/v1/audit-logs/',
    ]"
    note="冻结、重置密码、信用增减、押金增减均走 manage 接口并必填 reason；角色变更仅超级管理员。仅 admin 角色可见，运维访问后端会 403。"
  />
</template>
