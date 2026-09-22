<script setup lang="ts">
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="图书检索"
    stage="阶段 2 · 读者 Web 主线"
    :apis="['GET /api/v1/books/?search=', 'GET /api/v1/books/?isbn=&category=&author=', 'GET /api/v1/categories/']"
    note="支持书名/作者/ISBN/索书号模糊检索与精确过滤；返回 total_count 与 available_count，分页在 data.results。"
  />
</template>
