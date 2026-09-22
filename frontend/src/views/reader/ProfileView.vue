<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="个人中心"
    stage="阶段 2 · 读者 Web 主线"
    :apis="[
      'GET/PATCH /api/v1/readers/me/',
      'POST /api/v1/readers/verify-identity/',
      'POST /api/v1/readers/password/',
      'POST /api/v1/readers/phone/',
      'GET /api/v1/credit-entries/',
      'GET /api/v1/deposit-entries/',
    ]"
    note="实名核验需先勾选身份用途同意记录；改密后旧 access 立即失效，需重新登录。"
  />
</template>
