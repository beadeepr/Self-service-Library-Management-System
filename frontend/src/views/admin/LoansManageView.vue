<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="借还管理"
    stage="阶段 4 · 管理后台"
    :apis="[
      'GET /api/v1/loans/',
      'POST /api/v1/loans/borrow/',
      'POST /api/v1/loans/{id}/return/',
      'POST /api/v1/loans/{id}/remind/',
      'GET /api/v1/fines/',
    ]"
    note="全量借阅查询与异常兜底：管理员可代读者手工借书（borrow 传 reader）、催还、处理损坏归还。写操作均需幂等键。"
  />
</template>
