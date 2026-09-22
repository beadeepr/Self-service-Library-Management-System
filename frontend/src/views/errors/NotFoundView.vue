<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
</script>

<template>
  <div class="not-found">
    <el-result icon="warning" title="404" sub-title="没有找到这个页面">
      <template #extra>
        <el-button type="primary" @click="router.push({ path: auth.isAuthenticated ? auth.homePath() : '/reader/home' })">
          回到首页
        </el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.not-found {
  align-items: center;
  display: flex;
  justify-content: center;
  min-height: 100%;
}
</style>
