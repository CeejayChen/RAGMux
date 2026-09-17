<script setup lang="ts">
/**
 * 主视图：右侧管理区。未选中知识库时给引导，选中后按 tab 切换管理面板。
 */
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import * as api from '../api/client'
import type { KBDetail } from '../api/types'
import { useKBStore } from '../stores/kbs'
import DocumentsPanel from '../components/DocumentsPanel.vue'
import KBCreateDialog from '../components/KBCreateDialog.vue'
import QueryPanel from '../components/QueryPanel.vue'
import GraphPanel from '../components/GraphPanel.vue'
import KBSettingsPanel from '../components/KBSettingsPanel.vue'

const store = useKBStore()
const { selectedKBId, creating } = storeToRefs(store)

const detail = ref<KBDetail | null>(null)
const activeTab = ref('documents')

async function loadDetail() {
  if (!selectedKBId.value) {
    detail.value = null
    return
  }
  try {
    detail.value = await api.getKB(selectedKBId.value)
  } catch (err) {
    detail.value = null
    ElMessage.error((err as Error).message)
  }
}

watch(selectedKBId, loadDetail, { immediate: true })

function onCreated(kb: KBDetail) {
  store.creating = false
  store.refresh().catch(() => undefined)
  store.selectedKBId = kb.id
}

function onSaved() {
  loadDetail()
  store.refresh()
}
</script>

<template>
  <div class="kb-main">
    <template v-if="detail">
      <header class="kb-header">
        <h1 class="kb-title">{{ detail.name }}</h1>
        <span class="kb-desc">{{ detail.description || '（无描述）' }}</span>
        <el-tag size="small" :type="detail.instance_loaded ? 'success' : 'info'" effect="plain">
          {{ detail.instance_loaded ? '实例运行中' : '实例未加载' }}
        </el-tag>
      </header>
      <el-tabs v-model="activeTab" class="kb-tabs">
        <el-tab-pane label="文档" name="documents">
          <DocumentsPanel :kb-id="detail.id" />
        </el-tab-pane>
        <el-tab-pane label="检索测试" name="query" lazy>
          <QueryPanel :kb-id="detail.id" />
        </el-tab-pane>
        <el-tab-pane label="知识图谱" name="graph" lazy>
          <GraphPanel :kb-id="detail.id" />
        </el-tab-pane>
        <el-tab-pane label="设置" name="settings" lazy>
          <KBSettingsPanel :kb-id="detail.id" :detail="detail" @saved="onSaved" />
        </el-tab-pane>
      </el-tabs>
    </template>
    <template v-else>
      <div class="kb-empty">
        <h1 class="kb-title">RAGMux 知识库管理</h1>
        <p class="kb-desc">从左侧选择一个知识库进行管理，或创建新的知识库。</p>
        <el-empty description="未选中知识库">
          <el-button type="primary" @click="creating = true">新建知识库</el-button>
        </el-empty>
      </div>
    </template>
    <KBCreateDialog v-if="creating" @close="creating = false" @created="onCreated" />
  </div>
</template>
