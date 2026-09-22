<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="注册"
    stage="阶段 1 · 认证闭环"
    :apis="['GET /api/v1/auth/captcha/', 'POST /api/v1/auth/sms-code/', 'POST /api/v1/auth/register/']"
    note="先过图形验证码再取注册短信码；注册只能产生 reader 角色。密码需通过后端强度校验。"
  />
</template>
