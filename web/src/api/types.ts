/**
 * RAGMux API 客户端类型定义（与后端响应结构一一对应）。
 *
 * 知识库/模型配置等实体的 TypeScript 类型。
 */

export interface Profile {
  id: string
  name: string
  kind: 'llm' | 'embedding' | 'rerank'
  provider: string
  model: string
  base_url: string | null
  has_api_key: boolean
  dimension: number | null
  extra: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface KBStorageConfig {
  kv_storage: string
  vector_storage: string
  graph_storage: string
  doc_status_storage: string
}

export interface KBQueryDefaults {
  mode: string
  only_need_context: boolean
  response_type: string
  top_k: number
  chunk_top_k: number
}

export interface KBConfig {
  storage: KBStorageConfig
  chunk_token_size: number
  chunk_overlap_token_size: number
  llm_model_max_async: number
  embedding_func_max_async: number
  embedding_batch_num: number
  language: string
  query: KBQueryDefaults
  entity_types: string[] | null
}

export interface ProfileRef {
  id: string | null
  name: string | null
  provider: string
  model: string
}

export interface KB {
  id: string
  name: string
  description: string
  enabled: boolean
  created_at: string
  updated_at: string
  instance_loaded?: boolean
}

export interface KBDetail extends KB {
  config: KBConfig
  profiles: {
    llm: ProfileRef | null
    embedding: ProfileRef | null
    rerank: ProfileRef | null
  }
}

export interface RAGDocument {
  id: string
  status: string
  file_path: string
  content_summary: string
  content_length: number
  chunks_count: number | null
  error_msg: string | null
  created_at: string
  updated_at: string
  track_id: string | null
}

export interface PaginatedDocuments {
  documents: RAGDocument[]
  pagination: { page: number; page_size: number; total_count: number }
  status_counts: Record<string, number>
}

export interface QueryResultItem {
  kb_id: string
  kb_name: string
  ok: boolean
  response?: string
  error?: string
}

export interface GraphNode {
  id: string
  labels: string[]
  properties: Record<string, unknown>
}

export interface GraphEdge {
  id: string
  type: string | null
  source: string
  target: string
  properties: Record<string, unknown>
}

export interface KnowledgeGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  is_truncated: boolean
}
