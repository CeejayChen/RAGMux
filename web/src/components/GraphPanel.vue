<script setup lang="ts">
/**
 * 图谱浏览面板：标签选择 + 子图 SVG 可视化 + 节点/边详情。
 */
import { ElMessage } from 'element-plus'
import { defineProps, onMounted, ref } from 'vue'
import * as api from '../api/client'
import type { KnowledgeGraph } from '../api/types'
import { computeLayout } from './graphLayout'

const props = defineProps<{ kbId: string }>()

const labels = ref<string[]>([])
const selectedLabel = ref('*')
const graph = ref<KnowledgeGraph | null>(null)
const loading = ref(false)
const selectedNode = ref<{ id: string; labels: string[]; properties: Record<string, unknown> } | null>(null)

const WIDTH = 760
const HEIGHT = 480

interface RenderNode {
  id: string
  x: number
  y: number
  label: string
}
interface RenderEdge {
  x1: number
  y1: number
  x2: number
  y2: number
  label: string
}

const renderNodes = ref<RenderNode[]>([])
const renderEdges = ref<RenderEdge[]>([])

onMounted(async () => {
  try {
    labels.value = await api.graphLabels(props.kbId)
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
})

async function loadGraph() {
  loading.value = true
  selectedNode.value = null
  try {
    const data = await api.subgraph(props.kbId, {
      label: selectedLabel.value,
      max_depth: 3,
      max_nodes: 120,
    })
    graph.value = data
    const layout = computeLayout(
      data.nodes.map((node) => node.id),
      data.edges.map((edge) => ({ source: edge.source, target: edge.target })),
      WIDTH,
      HEIGHT,
    )
    renderNodes.value = data.nodes.map((node) => ({
      id: node.id,
      ...(layout.nodes.get(node.id) ?? { x: WIDTH / 2, y: HEIGHT / 2 }),
      label: node.labels[0] ?? node.id,
    }))
    const positionOf = new Map(renderNodes.value.map((node) => [node.id, node]))
    renderEdges.value = data.edges.map((edge) => ({
      x1: positionOf.get(edge.source)?.x ?? 0,
      y1: positionOf.get(edge.source)?.y ?? 0,
      x2: positionOf.get(edge.target)?.x ?? 0,
      y2: positionOf.get(edge.target)?.y ?? 0,
      label: String(edge.properties?.description ?? edge.properties?.relationship ?? edge.type ?? ''),
    }))
    if (data.nodes.length === 0) {
      ElMessage.info('该标签下暂无图谱节点')
    }
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function pickNode(node: RenderNode) {
  const found = graph.value?.nodes.find((item) => item.id === node.id)
  if (found) selectedNode.value = { id: found.id, labels: found.labels, properties: found.properties }
}
</script>

<template>
  <div>
    <div style="display: flex; gap: 10px; margin-bottom: 14px; align-items: center">
      <el-select v-model="selectedLabel" style="width: 220px" filterable placeholder="选择起始标签">
        <el-option value="*" label="*（随机起点）" />
        <el-option v-for="label in labels" :key="label" :value="label" :label="label" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="loadGraph">加载子图</el-button>
      <span v-if="graph" style="color: var(--el-text-color-secondary); font-size: 13px">
        {{ graph.nodes.length }} 节点 / {{ graph.edges.length }} 边
        <el-tag v-if="graph.is_truncated" size="small" type="warning" style="margin-left: 6px">已截断</el-tag>
      </span>
    </div>

    <el-card v-if="graph && graph.nodes.length" shadow="never" :body-style="{ padding: '8px' }">
      <svg
        :width="WIDTH"
        :height="HEIGHT"
        style="display: block; background: var(--el-fill-color-lighter); border-radius: 6px"
      >
        <g>
          <line
            v-for="(edge, index) in renderEdges"
            :key="index"
            :x1="edge.x1"
            :y1="edge.y1"
            :x2="edge.x2"
            :y2="edge.y2"
            stroke="var(--el-border-color)"
            stroke-width="1.5"
          />
        </g>
        <g>
          <circle
            v-for="node in renderNodes"
            :key="node.id"
            :cx="node.x"
            :cy="node.y"
            r="14"
            fill="var(--el-color-primary-light-7)"
            stroke="var(--el-color-primary)"
            stroke-width="1.5"
            style="cursor: pointer"
            @click="pickNode(node)"
          >
            <title>{{ node.label }}</title>
          </circle>
        </g>
        <g>
          <text
            v-for="node in renderNodes"
            :key="`t-${node.id}`"
            :x="node.x"
            :y="node.y + 4"
            text-anchor="middle"
            font-size="9"
            fill="var(--el-text-color-regular)"
            style="pointer-events: none; max-width: 24px"
          >
            {{ node.label.slice(0, 5) }}
          </text>
        </g>
      </svg>
    </el-card>
    <el-empty v-else-if="!loading" description="选择标签并加载子图" :image-size="64" />

    <el-drawer v-model="selectedNode" title="节点详情" size="360px">
      <div v-if="selectedNode">
        <h4 style="margin-top: 0">{{ selectedNode.id }}</h4>
        <p>
          <el-tag v-for="label in selectedNode.labels" :key="label" size="small" style="margin-right: 4px">
            {{ label }}
          </el-tag>
        </p>
        <pre class="mono" style="white-space: pre-wrap">{{
          JSON.stringify(selectedNode.properties, null, 2)
        }}</pre>
      </div>
    </el-drawer>
  </div>
</template>
