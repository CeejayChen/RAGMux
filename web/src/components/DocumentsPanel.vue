<script setup lang="ts">
/**
 * 文档管理面板：文本/文件导入、分页列表（状态轮询）、详情、删除。
 */
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import { defineProps, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as api from '../api/client'
import type { PaginatedDocuments, RAGDocument } from '../api/types'

const props = defineProps<{ kbId: string }>()

const listing = ref<PaginatedDocuments>({
  documents: [],
  pagination: { page: 1, page_size: 25, total_count: 0 },
  status_counts: {},
})
const loading = ref(false)
const query = reactive({ page: 1, page_size: 25, status_filter: '' })
const insertVisible = ref(false)
const insertText = ref('')
const uploading = ref(false)
const detail = ref<(RAGDocument & { content: string | null }) | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  parsing: '解析中',
  analyzing: '分析中',
  processing: '处理中',
  processed: '已完成',
  failed: '失败',
}

async function load() {
  loading.value = true
  try {
    listing.value = await api.listDocuments(props.kbId, {
      page: query.page,
      page_size: query.page_size,
      status_filter: query.status_filter || undefined,
    })
    schedulePollIfPending()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  query.page = 1
  load()
}

function onFileChange(file: UploadFile) {
  if (file.raw) onUpload(file.raw)
}

/** 存在进行中的任务时自动轮询（最多 60 次）。 */
function schedulePollIfPending() {
  const hasActive = listing.value.documents.some((doc) =>
    ['pending', 'parsing', 'analyzing', 'processing'].includes(doc.status),
  )
  if (!hasActive) return
  let ticks = 0
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(() => {
    ticks += 1
    if (ticks > 60 || !hasActiveDocs()) {
      clearInterval(pollTimer!)
      pollTimer = null
      load()
      return
    }
    api
      .listDocuments(props.kbId, { page: query.page, page_size: query.page_size })
      .then((data) => {
        listing.value = data
        if (!hasActiveDocs()) {
          clearInterval(pollTimer!)
          pollTimer = null
          load()
        }
      })
      .catch(() => undefined)
  }, 2000)
}

function hasActiveDocs(): boolean {
  return listing.value.documents.some((doc) =>
    ['pending', 'parsing', 'analyzing', 'processing'].includes(doc.status),
  )
}

async function submitInsert() {
  const texts = insertText.value
    .split('\n---\n')
    .map((t) => t.trim())
    .filter(Boolean)
  if (texts.length === 0) {
    ElMessage.warning('请输入文本；多份文本用单独一行 --- 分隔')
    return
  }
  try {
    const result = await api.insertTexts(props.kbId, texts)
    ElMessage.success(`已入队 ${result.queued} 份文本`)
    insertText.value = ''
    insertVisible.value = false
    query.page = 1
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function onUpload(file: File) {
  uploading.value = true
  try {
    await api.uploadFile(props.kbId, file)
    ElMessage.success(`已上传 ${file.name}`)
    query.page = 1
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    uploading.value = false
  }
}

async function openDetail(row: RAGDocument) {
  try {
    detail.value = await api.getDocument(props.kbId, row.id)
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function removeDoc(row: RAGDocument) {
  try {
    await ElMessageBox.confirm(
      `确定删除文档「${row.file_path}」？其 chunks 与图谱元素将一并清理。`,
      '删除文档',
      {
        type: 'warning',
      },
    )
  } catch {
    return
  }
  try {
    await api.deleteDocument(props.kbId, row.id)
    ElMessage.success('已删除')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div>
    <div style="display: flex; gap: 10px; margin-bottom: 14px; align-items: center">
      <el-button type="primary" @click="insertVisible = true">导入文本</el-button>
      <el-upload
        :show-file-list="false"
        :auto-upload="false"
        accept=".txt,.md,.markdown,.json,.csv,.html,.htm"
        @change="onFileChange"
      >
        <el-button :loading="uploading">上传文本文件</el-button>
      </el-upload>
      <span style="flex: 1" />
      <el-select
        v-model="query.status_filter"
        placeholder="全部状态"
        clearable
        style="width: 130px"
        @change="onFilterChange"
      >
        <el-option v-for="(label, value) in STATUS_LABELS" :key="value" :value="value" :label="label" />
      </el-select>
      <el-button @click="load">刷新</el-button>
    </div>

    <div v-if="Object.keys(listing.status_counts).length" style="margin-bottom: 12px">
      <el-tag
        v-for="(count, status) in listing.status_counts"
        :key="status"
        style="margin-right: 6px"
        :type="status === 'failed' ? 'danger' : status === 'processed' ? 'success' : 'info'"
      >
        {{ STATUS_LABELS[status] || status }}: {{ count }}
      </el-tag>
    </div>

    <el-table :data="listing.documents" v-loading="loading" size="small">
      <el-table-column prop="file_path" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag
            size="small"
            :type="row.status === 'processed' ? 'success' : row.status === 'failed' ? 'danger' : 'info'"
          >
            {{ STATUS_LABELS[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="chunks_count" label="块数" width="70" />
      <el-table-column prop="content_length" label="长度" width="90" />
      <el-table-column prop="updated_at" label="更新时间" width="170" show-overflow-tooltip />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
          <el-button link type="danger" size="small" @click="removeDoc(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="listing.pagination.total_count > listing.pagination.page_size"
      style="margin-top: 12px; justify-content: flex-end"
      layout="prev, pager, next, total"
      :total="listing.pagination.total_count"
      :page-size="query.page_size"
      :current-page="query.page"
      @current-change="
        (page: number) => {
          query.page = page
          load()
        }
      "
    />

    <el-dialog v-model="insertVisible" title="导入文本" width="640px">
      <el-input
        v-model="insertText"
        type="textarea"
        :rows="12"
        placeholder="粘贴文档内容；多份文本之间用单独一行 --- 分隔"
      />
      <template #footer>
        <el-button @click="insertVisible = false">取消</el-button>
        <el-button type="primary" @click="submitInsert">入队导入</el-button>
      </template>
    </el-dialog>

    <el-dialog
      :model-value="!!detail"
      :title="detail?.file_path || '文档详情'"
      width="680px"
      @close="detail = null"
    >
      <div v-if="detail">
        <p style="margin-top: 0">
          <el-tag size="small">{{ STATUS_LABELS[detail.status] || detail.status }}</el-tag>
          <span style="margin-left: 8px; color: var(--el-text-color-secondary)">
            {{ detail.chunks_count ?? '-' }} 块 · {{ detail.content_length }} 字符
          </span>
        </p>
        <p v-if="detail.error_msg" style="color: var(--el-color-danger)">错误：{{ detail.error_msg }}</p>
        <el-input type="textarea" :rows="16" :model-value="detail.content || '（内容尚未生成）'" readonly />
      </div>
    </el-dialog>
  </div>
</template>
