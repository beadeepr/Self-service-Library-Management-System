<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="登录"
    stage="阶段 1 · 认证闭环"
    :apis="['POST /api/v1/auth/login/', 'POST /api/v1/auth/sms-code/', 'GET /api/v1/auth/captcha/']"
    note="手机号 + 密码登录；支持模拟短信验证码登录（响应含 simulation_code）。连续 5 次错误锁定 15 分钟。"
  />
</template>
