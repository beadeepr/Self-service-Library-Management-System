<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="自助终端首页"
    stage="阶段 3 · Kiosk 借还"
    :apis="['POST /api/v1/auth/login/', 'POST /api/v1/auth/sms-login/']"
    note="读者刷卡（演示以手机号 + 密码/短信码签到）后以读者身份进入借书、还书与门禁操作；未签到只能浏览。"
  />
</template>
