/** 当前读者资料（信用、押金、实名状态），供页头与个人中心共用。 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { UserProfile } from '@/api/auth'
import { fetchMe } from '@/api/readers'

export const useReaderStore = defineStore('reader', () => {
  const profile = ref<UserProfile | null>(null)
  const loading = ref(false)

  const displayName = computed(() => profile.value?.first_name || profile.value?.phone || '读者')
  const creditLevel = computed(() => profile.value?.credit_level ?? 'normal')
  const isVerified = computed(() => !!profile.value?.verified)

  /** 同一会话内复用已加载的资料，force=true 用于修改后强制刷新。 */
  async function load(force = false): Promise<UserProfile | null> {
    if (profile.value && !force) return profile.value
    loading.value = true
    try {
      profile.value = await fetchMe()
      return profile.value
    } finally {
      loading.value = false
    }
  }

  function set(next: UserProfile | null): void {
    profile.value = next
  }

  function reset(): void {
    profile.value = null
  }

  return { profile, loading, displayName, creditLevel, isVerified, load, set, reset }
})
