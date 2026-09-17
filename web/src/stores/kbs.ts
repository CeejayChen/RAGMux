/**
 * 全局状态：知识库扁平列表（Pinia store）。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as api from '../api/client'
import type { KB } from '../api/types'

export const useKBStore = defineStore('kbs', () => {
  const kbs = ref<KB[]>([])
  const loading = ref(false)
  const selectedKBId = ref<string | null>(null)
  /** 新建知识库对话框开关（侧栏与主区共用）。 */
  const creating = ref(false)

  const selectedKB = computed(() => kbs.value.find((kb) => kb.id === selectedKBId.value) ?? null)

  async function refresh() {
    loading.value = true
    try {
      kbs.value = await api.listKBs()
      // 选中的库若已被删除则清除选中态
      if (selectedKBId.value && !kbs.value.some((kb) => kb.id === selectedKBId.value)) {
        selectedKBId.value = null
      }
    } finally {
      loading.value = false
    }
  }

  return { kbs, loading, selectedKBId, selectedKB, creating, refresh }
})
