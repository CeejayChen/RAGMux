/**
 * RAGMux API 客户端：统一封装 axios 实例与全部后端接口调用。
 *
 * 后端错误返回 { detail: string }，这里统一抛出含可读信息的 Error。
 */
import axios from 'axios'
import type {
  KB,
  KBDetail,
  KBConfig,
  KnowledgeGraph,
  PaginatedDocuments,
  Profile,
  QueryResultItem,
  RAGDocument,
} from './types'

const http = axios.create({ baseURL: '/api', timeout: 120_000 })

function detailOf(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail)
    return error.message
  }
  return String(error)
}

// 拦截器：把 axios 错误转成可读 Error，调用方只需 catch 消息文本
http.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(new Error(detailOf(error))),
)

// ---------------------------------------------------------------- 系统

export async function getHealth(): Promise<{ status: string; version: string }> {
  const { data } = await http.get('/health')
  return data
}

export interface Overview {
  version: string
  registry: { kbs: number; profiles: number }
  instances: { loaded: number; capacity: number; loaded_ids: string[]; active_ids: string[] }
}

export async function getOverview(): Promise<Overview> {
  const { data } = await http.get('/system/overview')
  return data
}

// ---------------------------------------------------------------- 模型服务目录

export interface OllamaModel {
  name: string
  size?: number
}

export const listOllamaModels = async (baseUrl: string): Promise<OllamaModel[]> =>
  (await http.get('/providers/ollama/models', { params: { base_url: baseUrl }, timeout: 15_000 })).data.models

// ---------------------------------------------------------------- 模型配置

export interface ProfilePayload {
  name: string
  kind: string
  provider: string
  model: string
  base_url?: string | null
  api_key?: string | null
  dimension?: number | null
  extra?: Record<string, unknown> | null
}

export const listProfiles = async (kind?: string): Promise<Profile[]> =>
  (await http.get('/profiles', { params: kind ? { kind } : {} })).data.profiles

export const createProfile = async (payload: ProfilePayload): Promise<Profile> =>
  (await http.post('/profiles', payload)).data

export const updateProfile = async (id: string, payload: Partial<ProfilePayload>): Promise<Profile> =>
  (await http.patch(`/profiles/${id}`, payload)).data

export const deleteProfile = async (id: string): Promise<void> => {
  await http.delete(`/profiles/${id}`)
}

export const testProfile = async (id: string): Promise<{ ok: boolean; detail: string }> =>
  (await http.post(`/profiles/${id}/test`)).data

// ---------------------------------------------------------------- 知识库

export interface KBCreatePayload {
  name: string
  embedding_profile_id: string
  group_id?: string | null
  description?: string
  llm_profile_id?: string | null
  rerank_profile_id?: string | null
  config?: Partial<KBConfig>
}

export interface KBUpdatePayload {
  name?: string
  description?: string
  enabled?: boolean
  llm_profile_id?: string | null
  embedding_profile_id?: string
  rerank_profile_id?: string | null
  config?: Record<string, unknown>
}

export const listKBs = async (): Promise<KB[]> => (await http.get('/kbs')).data.kbs

export const createKB = async (payload: KBCreatePayload): Promise<KBDetail> =>
  (await http.post('/kbs', payload)).data

export const getKB = async (id: string): Promise<KBDetail> => (await http.get(`/kbs/${id}`)).data

export const updateKB = async (id: string, payload: KBUpdatePayload): Promise<KBDetail> =>
  (await http.patch(`/kbs/${id}`, payload)).data

export const deleteKB = async (id: string, removeData = true): Promise<void> => {
  await http.delete(`/kbs/${id}`, { params: { remove_data: removeData } })
}

export const invalidateKB = async (id: string): Promise<{ invalidated: boolean }> =>
  (await http.post(`/kbs/${id}/invalidate`)).data

export interface KBStats {
  kb_id: string
  status_counts: Record<string, number>
  pipeline: Record<string, unknown>
  instance_loaded: boolean
}

export const getKBStats = async (id: string): Promise<KBStats> => (await http.get(`/kbs/${id}/stats`)).data

// ---------------------------------------------------------------- 文档

export interface DocumentListParams {
  page?: number
  page_size?: number
  status_filter?: string
  sort_field?: string
  sort_direction?: string
}

export const listDocuments = async (
  kbId: string,
  params: DocumentListParams = {},
): Promise<PaginatedDocuments> => (await http.get(`/kbs/${kbId}/documents`, { params })).data

export const insertTexts = async (
  kbId: string,
  texts: string[],
  filePaths?: string[],
): Promise<{ track_id: string; queued: number }> =>
  (await http.post(`/kbs/${kbId}/documents/text`, { texts, file_paths: filePaths }, { timeout: 30_000 })).data

export const uploadFile = async (
  kbId: string,
  file: File,
): Promise<{ track_id: string; file_path: string }> => {
  const form = new FormData()
  form.append('file', file)
  return (
    await http.post(`/kbs/${kbId}/documents/file`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  ).data
}

export const getDocument = async (
  kbId: string,
  docId: string,
): Promise<RAGDocument & { content: string | null }> =>
  (await http.get(`/kbs/${kbId}/documents/${docId}`)).data

export const deleteDocument = async (
  kbId: string,
  docId: string,
): Promise<{ status: string; message: string }> => (await http.delete(`/kbs/${kbId}/documents/${docId}`)).data

// ---------------------------------------------------------------- 查询

export interface QueryPayload {
  query: string
  mode?: string
  only_need_context?: boolean
  response_type?: string
  top_k?: number
  chunk_top_k?: number
}

export const queryKB = async (
  kbId: string,
  payload: QueryPayload,
): Promise<{ response: string; mode: string }> => (await http.post(`/kbs/${kbId}/query`, payload)).data

export const queryMultiKB = async (
  kbIds: string[],
  payload: QueryPayload,
): Promise<{ results: QueryResultItem[] }> => (await http.post('/query', { kb_ids: kbIds, ...payload })).data

// ---------------------------------------------------------------- 图谱

export const graphLabels = async (kbId: string): Promise<string[]> =>
  (await http.get(`/kbs/${kbId}/graph/labels`)).data.labels

export const subgraph = async (
  kbId: string,
  params: { label?: string; max_depth?: number; max_nodes?: number },
): Promise<KnowledgeGraph> => (await http.get(`/kbs/${kbId}/graph`, { params })).data
