<script setup lang="ts">
/**
 * 左侧知识库列表：选择、新建、重命名、删除（扁平结构）。
 */
import { Collection, MoreFilled, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted } from 'vue'
import * as api from '../api/client'
import { useKBStore } from '../stores/kbs'

const store = useKBStore()

onMounted(() => {
  store.refresh().catch((err: Error) => ElMessage.error(err.message))
})

function select(kbId: string) {
  store.selectedKBId = kbId
}

async function renameKB(kbId: string, currentName: string) {
  try {
    const { value } = await ElMessageBox.prompt('新的知识库名称', '重命名知识库', {
      inputValue: currentName,
      inputPattern: /\S+/,
      inputErrorMessage: '不能为空',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await api.updateKB(kbId, { name: value.trim() })
    await store.refresh()
    ElMessage.success('已重命名')
  } catch {
    return
  }
}

async function removeKB(kbId: string, name: string) {
  try {
    await ElMessageBox.confirm(
      `确定删除知识库「${name}」？其全部文档与图谱数据将被清除，不可恢复。`,
      '删除知识库',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await api.deleteKB(kbId)
    await store.refresh()
    ElMessage.success('知识库已删除')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}
</script>

<template>
  <div class="kb-list">
    <div class="kb-list-actions">
      <el-button type="primary" :icon="Plus" @click="store.creating = true">新建知识库</el-button>
      <el-button :icon="Refresh" title="刷新" @click="store.refresh()" />
    </div>

    <div v-if="store.loading && store.kbs.length === 0" class="kb-list-hint">加载中…</div>
    <el-empty
      v-else-if="store.kbs.length === 0"
      description="还没有知识库，点击上方按钮创建"
      :image-size="60"
    />
    <ul v-else class="kb-items">
      <li
        v-for="kb in store.kbs"
        :key="kb.id"
        class="kb-item"
        :class="{ active: kb.id === store.selectedKBId, disabled: !kb.enabled }"
        @click="select(kb.id)"
      >
        <el-icon class="kb-icon"><collection /></el-icon>
        <span class="kb-name" :title="kb.description || kb.name">{{ kb.name }}</span>
        <el-tag v-if="kb.instance_loaded" size="small" class="kb-dot" type="success" effect="plain"
          >运行中</el-tag
        >
        <el-dropdown
          trigger="click"
          size="small"
          @command="(cmd: string) => (cmd === 'rename' ? renameKB(kb.id, kb.name) : removeKB(kb.id, kb.name))"
        >
          <el-icon class="kb-more" @click.stop><more-filled /></el-icon>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="rename">重命名</el-dropdown-item>
              <el-dropdown-item command="delete" divided>删除知识库</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </li>
    </ul>
  </div>
</template>
