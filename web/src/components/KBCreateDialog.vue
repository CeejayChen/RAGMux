<script setup lang="ts">
/**
 * 新建知识库对话框：名称/描述/模型绑定/基础参数。
 */
import { ElMessage } from 'element-plus'
import { defineEmits, onMounted, reactive, ref } from 'vue'
import * as api from '../api/client'
import type { KBConfig, KBDetail, Profile } from '../api/types'

const emit = defineEmits<{ (e: 'close'): void; (e: 'created', kb: KBDetail): void }>()

const form = reactive({
  name: '',
  description: '',
  llm_profile_id: '',
  embedding_profile_id: '',
  rerank_profile_id: '',
  chunk_token_size: 1200,
  chunk_overlap_token_size: 100,
})

const llmProfiles = ref<Profile[]>([])
const embeddingProfiles = ref<Profile[]>([])
const rerankProfiles = ref<Profile[]>([])
const submitting = ref(false)
const noEmbeddingProfile = ref(false)

onMounted(async () => {
  try {
    const [llm, embedding, rerank] = await Promise.all([
      api.listProfiles('llm'),
      api.listProfiles('embedding'),
      api.listProfiles('rerank'),
    ])
    llmProfiles.value = llm
    embeddingProfiles.value = embedding
    rerankProfiles.value = rerank
    if (embedding.length === 0) {
      noEmbeddingProfile.value = true
    }
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
})

async function submit() {
  if (!form.name.trim() || !form.embedding_profile_id) {
    ElMessage.warning('请填写名称并选择 embedding 配置')
    return
  }
  submitting.value = true
  const config: Partial<KBConfig> = {
    chunk_token_size: form.chunk_token_size,
    chunk_overlap_token_size: form.chunk_overlap_token_size,
  }
  try {
    const kb = await api.createKB({
      name: form.name.trim(),
      description: form.description,
      embedding_profile_id: form.embedding_profile_id,
      llm_profile_id: form.llm_profile_id || null,
      rerank_profile_id: form.rerank_profile_id || null,
      config,
    })
    ElMessage.success('知识库已创建')
    emit('created', kb)
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="true"
    title="新建知识库"
    width="560px"
    @close="emit('close')"
    :close-on-click-modal="false"
  >
    <el-alert
      v-if="noEmbeddingProfile"
      type="warning"
      :closable="false"
      style="margin-bottom: 14px"
    >
      <template #title>
        尚无模型配置——先到
        <router-link to="/profiles" style="margin: 0 4px">模型配置</router-link>
        页创建一个 Embedding 配置（推荐 Ollama + qwen3-embedding 系列），再回来新建知识库。
      </template>
    </el-alert>
    <el-form label-width="110px">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" placeholder="知识库唯一名称" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="（可选）" />
      </el-form-item>
      <el-form-item label="Embedding" required>
        <el-select v-model="form.embedding_profile_id" placeholder="选择 embedding 配置" style="width: 100%">
          <el-option
            v-for="p in embeddingProfiles"
            :key="p.id"
            :value="p.id"
            :label="`${p.name}（${p.provider} · ${p.model} · ${p.dimension}维）`"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="LLM">
        <el-select
          v-model="form.llm_profile_id"
          placeholder="不选则使用内置 mock（先建库后绑模型）"
          clearable
          style="width: 100%"
        >
          <el-option
            v-for="p in llmProfiles"
            :key="p.id"
            :value="p.id"
            :label="`${p.name}（${p.provider} · ${p.model}）`"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="Rerank">
        <el-select v-model="form.rerank_profile_id" placeholder="（可选）" clearable style="width: 100%">
          <el-option
            v-for="p in rerankProfiles"
            :key="p.id"
            :value="p.id"
            :label="`${p.name}（${p.provider} · ${p.model}）`"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="分块大小">
        <el-input-number v-model="form.chunk_token_size" :min="128" :max="8192" :step="64" />
        <span style="margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px">重叠</span>
        <el-input-number
          v-model="form.chunk_overlap_token_size"
          :min="0"
          :max="1024"
          :step="20"
          style="margin-left: 8px"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">创建</el-button>
    </template>
  </el-dialog>
</template>
