<script setup lang="ts">
/**
 * 检索测试面板：单库查询（5 种模式），展示回答与引用。
 */
import { ElMessage } from 'element-plus'
import { defineProps, reactive, ref } from 'vue'
import * as api from '../api/client'

const props = defineProps<{ kbId: string }>()

const form = reactive({
  query: '',
  mode: 'mix',
  only_need_context: false,
  top_k: undefined as number | undefined,
})
const answer = ref('')
const context = ref('')
const loading = ref(false)

const MODES = [
  { value: 'mix', label: 'mix（混合）' },
  { value: 'hybrid', label: 'hybrid（本地+全局）' },
  { value: 'local', label: 'local（实体）' },
  { value: 'global', label: 'global（主题）' },
  { value: 'naive', label: 'naive（朴素向量）' },
  { value: 'bypass', label: 'bypass（直连 LLM）' },
]

async function run() {
  if (!form.query.trim()) {
    ElMessage.warning('请输入查询内容')
    return
  }
  loading.value = true
  answer.value = ''
  context.value = ''
  try {
    const result = await api.queryKB(props.kbId, {
      query: form.query.trim(),
      mode: form.mode,
      only_need_context: form.only_need_context,
      top_k: form.top_k,
    })
    answer.value = result.response ?? ''
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <el-form inline>
      <el-form-item>
        <el-select v-model="form.mode" style="width: 180px">
          <el-option v-for="m in MODES" :key="m.value" :value="m.value" :label="m.label" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-input-number v-model="form.top_k" :min="1" :max="100" placeholder="top_k" style="width: 120px" />
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="form.only_need_context">仅返回上下文</el-checkbox>
      </el-form-item>
    </el-form>
    <div style="display: flex; gap: 8px; margin-bottom: 16px">
      <el-input v-model="form.query" placeholder="输入查询内容，回车执行" @keyup.enter="run" clearable />
      <el-button type="primary" :loading="loading" @click="run">查询</el-button>
    </div>
    <el-card v-if="answer" shadow="never">
      <template #header>回答</template>
      <div style="white-space: pre-wrap; line-height: 1.7">{{ answer }}</div>
    </el-card>
    <el-empty v-else-if="!loading" description="尚无查询结果" :image-size="64" />
  </div>
</template>
