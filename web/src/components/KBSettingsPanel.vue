<script setup lang="ts">
/**
 * 知识库设置面板：基础信息、启停、构建参数与实例控制。
 */
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import * as api from '../api/client'
import type { KBConfig, KBDetail } from '../api/types'

const props = defineProps<{ kbId: string; detail: KBDetail }>()
const emit = defineEmits<{ (e: 'saved'): void }>()

const form = reactive({
  name: props.detail.name,
  description: props.detail.description,
})
const saving = ref(false)

const advanced = ref<KBConfig>(JSON.parse(JSON.stringify(props.detail.config)) as KBConfig)

function diffAdvanced(): Record<string, unknown> | null {
  // 与后端 KBConfig 对齐：仅收集发生变化的顶层字段（storage/query 整体提交）
  const changes: Record<string, unknown> = {}
  const original = props.detail.config as unknown as Record<string, unknown>
  for (const [key, value] of Object.entries(advanced.value)) {
    if (JSON.stringify(value) !== JSON.stringify(original[key])) {
      changes[key] = value
    }
  }
  return Object.keys(changes).length ? changes : null
}

async function save() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = {}
    if (form.name !== props.detail.name) payload.name = form.name
    if (form.description !== props.detail.description) payload.description = form.description
    const configChanges = diffAdvanced()
    if (configChanges) payload.config = configChanges
    if (Object.keys(payload).length === 0) {
      ElMessage.info('没有需要保存的修改')
      return
    }
    await api.updateKB(props.kbId, payload)
    ElMessage.success('已保存；构建相关变更会使实例失效并按新配置重建')
    emit('saved')
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(enabled: boolean) {
  try {
    await api.updateKB(props.kbId, { enabled })
    ElMessage.success(enabled ? '知识库已启用' : '知识库已停用')
    emit('saved')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function invalidate() {
  try {
    const result = await api.invalidateKB(props.kbId)
    ElMessage.success(result.invalidated ? '实例已驱逐，下次访问按注册表重建' : '实例当前未加载')
    emit('saved')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}
</script>

<template>
  <el-form label-width="130px" style="max-width: 640px">
    <el-form-item label="名称">
      <el-input v-model="form.name" />
    </el-form-item>
    <el-form-item label="描述">
      <el-input v-model="form.description" type="textarea" :rows="2" />
    </el-form-item>
    <el-form-item label="模型绑定">
      <div class="mono" style="line-height: 1.9">
        <div>LLM：{{ detail.profiles.llm?.name || '（未绑定）' }} · {{ detail.profiles.llm?.model }}</div>
        <div>Embedding：{{ detail.profiles.embedding?.name }} · {{ detail.profiles.embedding?.model }}</div>
        <div>
          Rerank：{{ detail.profiles.rerank?.name || '（未绑定）' }} ·
          {{ detail.profiles.rerank?.model || '-' }}
        </div>
      </div>
    </el-form-item>
    <el-form-item label="启用状态">
      <el-switch :model-value="detail.enabled" @change="(value: unknown) => toggleEnabled(Boolean(value))" />
    </el-form-item>

    <el-divider>构建参数（改后自动重建实例）</el-divider>
    <el-collapse>
      <el-collapse-item title="分块与存储参数" name="adv">
        <el-form label-width="150px">
          <el-form-item label="chunk_token_size">
            <el-input-number v-model="advanced.chunk_token_size" :min="128" :max="8192" />
          </el-form-item>
          <el-form-item label="chunk_overlap">
            <el-input-number v-model="advanced.chunk_overlap_token_size" :min="0" :max="1024" />
          </el-form-item>
          <el-form-item label="抽取语言">
            <el-input v-model="advanced.language" />
          </el-form-item>
          <el-form-item label="KV 存储">
            <el-input v-model="advanced.storage.kv_storage" class="mono" />
          </el-form-item>
          <el-form-item label="向量存储">
            <el-input v-model="advanced.storage.vector_storage" class="mono" />
          </el-form-item>
          <el-form-item label="图谱存储">
            <el-input v-model="advanced.storage.graph_storage" class="mono" />
          </el-form-item>
          <el-form-item label="DocStatus 存储">
            <el-input v-model="advanced.storage.doc_status_storage" class="mono" />
          </el-form-item>
          <el-form-item label="默认查询模式">
            <el-select v-model="advanced.query.mode" style="width: 160px">
              <el-option
                v-for="m in ['local', 'global', 'hybrid', 'naive', 'mix', 'bypass']"
                :key="m"
                :value="m"
                :label="m"
              />
            </el-select>
          </el-form-item>
        </el-form>
      </el-collapse-item>
    </el-collapse>

    <el-form-item style="margin-top: 18px">
      <el-button type="primary" :loading="saving" @click="save">保存修改</el-button>
      <el-button @click="invalidate">驱逐实例</el-button>
    </el-form-item>
  </el-form>
</template>
