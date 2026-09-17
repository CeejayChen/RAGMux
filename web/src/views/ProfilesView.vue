<script setup lang="ts">
/**
 * 模型配置页：LLM / Embedding / Rerank 配置的运行时管理与连通性测试。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import * as api from '../api/client'
import type { Profile } from '../api/types'

const profiles = ref<Profile[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const testingId = ref<string | null>(null)
const editingId = ref<string | null>(null)

const KIND_LABELS: Record<string, string> = { llm: 'LLM', embedding: 'Embedding', rerank: 'Rerank' }

const form = reactive({
  name: '',
  kind: 'llm',
  provider: 'openai',
  model: '',
  base_url: '',
  api_key: '',
  dimension: undefined as number | undefined,
})

// 模型策略：优先开源模型——Ollama 排首位，新建配置默认选中
const PROVIDERS_BY_KIND: Record<string, { value: string; label: string }[]> = {
  llm: [
    { value: 'ollama', label: 'Ollama（开源模型）' },
    { value: 'openai', label: 'OpenAI 兼容' },
    { value: 'mock', label: 'mock（离线桩）' },
  ],
  embedding: [
    { value: 'ollama', label: 'Ollama（开源模型）' },
    { value: 'openai', label: 'OpenAI 兼容' },
    { value: 'mock', label: 'mock（离线桩）' },
  ],
  rerank: [
    { value: 'rerank_api', label: '通用 /rerank API' },
    { value: 'mock', label: 'mock（离线桩）' },
  ],
}

// ---------------- Ollama 模型目录 ----------------
const ollamaModels = ref<{ name: string }[]>([])
const ollamaLoading = ref(false)

async function fetchOllamaModels() {
  if (!form.base_url.trim()) {
    ElMessage.warning('请先填写 Ollama 服务地址')
    return
  }
  ollamaLoading.value = true
  try {
    ollamaModels.value = await api.listOllamaModels(form.base_url.trim())
    if (ollamaModels.value.length === 0) ElMessage.info('该 Ollama 服务未安装任何模型')
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    ollamaLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    profiles.value = await api.listProfiles()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCreate(kind: string) {
  editingId.value = null
  ollamaModels.value = []
  Object.assign(form, {
    name: '',
    kind,
    // 开源优先：llm/embedding 默认 ollama
    provider: kind === 'rerank' ? PROVIDERS_BY_KIND[kind][0].value : 'ollama',
    model: '',
    base_url: '',
    api_key: '',
    dimension: undefined,
  })
  dialogVisible.value = true
}

function openEdit(profile: Profile) {
  editingId.value = profile.id
  ollamaModels.value = []
  Object.assign(form, {
    name: profile.name,
    kind: profile.kind,
    provider: profile.provider,
    model: profile.model,
    base_url: profile.base_url ?? '',
    api_key: '',
    dimension: profile.dimension ?? undefined,
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim() || !form.model.trim()) {
    ElMessage.warning('名称与模型名不能为空')
    return
  }
  if (form.kind === 'embedding' && form.provider !== 'mock' && !form.dimension) {
    ElMessage.warning('embedding 配置必须填写向量维度')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.updateProfile(editingId.value, {
        name: form.name.trim(),
        provider: form.provider,
        model: form.model.trim(),
        base_url: form.base_url || null,
        dimension: form.dimension ?? null,
        ...(form.api_key ? { api_key: form.api_key } : {}),
      })
      ElMessage.success('已保存；引用它的知识库实例将自动失效重建')
    } else {
      await api.createProfile({
        name: form.name.trim(),
        kind: form.kind,
        provider: form.provider,
        model: form.model.trim(),
        base_url: form.base_url || null,
        api_key: form.api_key || null,
        dimension: form.dimension ?? null,
      })
      ElMessage.success('模型配置已创建')
    }
    dialogVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    saving.value = false
  }
}

async function test(profile: Profile) {
  testingId.value = profile.id
  try {
    const result = await api.testProfile(profile.id)
    ElMessage.success(`${profile.name}: ${result.detail}`)
  } catch (err) {
    ElMessage.error(`${profile.name}: ${(err as Error).message}`)
  } finally {
    testingId.value = null
  }
}

async function remove(profile: Profile) {
  try {
    await ElMessageBox.confirm(`确定删除模型配置「${profile.name}」？`, '删除', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.deleteProfile(profile.id)
    ElMessage.success('已删除')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">模型配置</h1>
    <p class="page-sub">
      LLM / Embedding / Rerank 的连接配置。知识库通过名称引用这些配置，修改后引用它的实例自动重建。
    </p>

    <div style="display: flex; gap: 8px; margin-bottom: 14px">
      <el-button type="primary" @click="openCreate('llm')">新建 LLM</el-button>
      <el-button type="primary" plain @click="openCreate('embedding')">新建 Embedding</el-button>
      <el-button plain @click="openCreate('rerank')">新建 Rerank</el-button>
      <span style="flex: 1" />
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table :data="profiles" v-loading="loading" size="small">
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ KIND_LABELS[row.kind] || row.kind }}</template>
      </el-table-column>
      <el-table-column prop="provider" label="Provider" width="110" />
      <el-table-column prop="model" label="模型" min-width="160" class-name="mono" />
      <el-table-column
        prop="base_url"
        label="Base URL"
        min-width="200"
        show-overflow-tooltip
        class-name="mono"
      />
      <el-table-column label="维度" width="70">
        <template #default="{ row }">{{ row.dimension ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="密钥" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="row.has_api_key ? 'success' : 'info'">{{
            row.has_api_key ? '已设' : '无'
          }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :loading="testingId === row.id" @click="test(row)"
            >测试</el-button
          >
          <el-button link size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模型配置' : '新建模型配置'" width="520px">
      <el-form label-width="100px">
        <el-form-item label="类型">
          <el-select
            v-model="form.kind"
            :disabled="!!editingId"
            @change="form.provider = PROVIDERS_BY_KIND[form.kind][0].value"
          >
            <el-option v-for="(label, value) in KIND_LABELS" :key="value" :value="value" :label="label" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Provider">
          <el-select v-model="form.provider">
            <el-option
              v-for="p in PROVIDERS_BY_KIND[form.kind]"
              :key="p.value"
              :value="p.value"
              :label="p.label"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名">
          <template v-if="form.provider === 'ollama'">
            <div style="display: flex; gap: 8px; width: 100%">
              <el-select
                v-model="form.model"
                filterable
                allow-create
                default-first-option
                placeholder="填写或从服务拉取模型名"
                style="flex: 1"
              >
                <el-option v-for="m in ollamaModels" :key="m.name" :value="m.name" :label="m.name" />
              </el-select>
              <el-button :loading="ollamaLoading" @click="fetchOllamaModels">拉取模型列表</el-button>
            </div>
          </template>
          <el-input v-else v-model="form.model" placeholder="例如 qwen3:8b / gpt-4o-mini" />
        </el-form-item>
        <template v-if="form.provider !== 'mock'">
          <el-form-item label="服务地址">
            <el-input
              v-model="form.base_url"
              :placeholder="
                form.provider === 'ollama' ? 'http://127.0.0.1:11434' : 'https://api.example.com/v1'
              "
            />
          </el-form-item>
          <el-form-item v-if="form.provider !== 'ollama'" label="API Key">
            <el-input
              v-model="form.api_key"
              type="password"
              show-password
              :placeholder="editingId ? '留空保持不变' : 'sk-...'"
            />
          </el-form-item>
          <el-form-item v-if="form.kind === 'embedding'" label="向量维度">
            <el-input-number v-model="form.dimension" :min="1" :max="4096" />
            <span
              v-if="form.provider === 'ollama'"
              style="margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px"
            >
              须与模型原生输出一致（qwen3-embedding:0.6b=1024、bge-m3=1024、nomic-embed-text=768）
            </span>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
