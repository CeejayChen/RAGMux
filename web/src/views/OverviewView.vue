<script setup lang="ts">
/**
 * 系统概览页：注册表统计 + 实例驻留状态。
 */
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { getOverview, type Overview } from '../api/client'

const overview = ref<Overview | null>(null)

onMounted(async () => {
  try {
    overview.value = await getOverview()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">系统概览</h1>
    <p class="page-sub">单进程服务：注册表（SQLite）+ 按需加载的 LightRAG 实例池。</p>

    <template v-if="overview">
      <el-row :gutter="14" style="margin-bottom: 18px">
        <el-col :span="12">
          <el-card shadow="never">
            <el-statistic title="知识库数" :value="overview.registry.kbs" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <el-statistic title="模型配置数" :value="overview.registry.profiles" />
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never">
        <template #header>
          实例池（{{ overview.instances.loaded }}/{{ overview.instances.capacity }}）
          <el-tag size="small" style="margin-left: 8px">RAGMux v{{ overview.version }}</el-tag>
        </template>
        <el-empty
          v-if="overview.instances.loaded === 0"
          description="暂无驻留实例（按需懒加载）"
          :image-size="64"
        />
        <el-table v-else :data="overview.instances.loaded_ids" size="small">
          <el-table-column label="kb_id" prop="id" class-name="mono" />
          <el-table-column label="状态" width="140">
            <template #default="{ row }">
              <el-tag size="small" :type="overview.instances.active_ids.includes(row) ? 'success' : 'info'">
                {{ overview.instances.active_ids.includes(row) ? '使用中' : '驻留空闲' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
    <el-skeleton v-else :rows="6" animated />
  </div>
</template>
