/**
 * 极简力导向布局：为图谱 SVG 渲染计算节点坐标。
 * 迭代式斥力 + 弹簧引力 + 位置阻尼，规模（≤200 节点）下足够流畅。
 */
export interface LayoutNode {
  id: string
  x: number
  y: number
}

export interface LayoutEdge {
  source: string
  target: string
}

export interface LayoutResult {
  nodes: Map<string, { x: number; y: number }>
  width: number
  height: number
}

/** 计算布局；迭代次数与画布尺寸可调。 */
export function computeLayout(
  nodes: string[],
  edges: LayoutEdge[],
  width = 760,
  height = 480,
  iterations = 150,
): LayoutResult {
  const ids = [...new Set(nodes)]
  const positions = new Map<string, { x: number; y: number }>()
  if (ids.length === 0) return { nodes: positions, width, height }

  // 初始：圆形分布，避免重叠导致斥力爆炸
  const radius = Math.min(width, height) / 2.5
  ids.forEach((id, index) => {
    const angle = (2 * Math.PI * index) / ids.length
    positions.set(id, {
      x: width / 2 + radius * Math.cos(angle),
      y: height / 2 + radius * Math.sin(angle),
    })
  })

  const adjacency = new Map<string, string[]>()
  for (const edge of edges) {
    if (!positions.has(edge.source) || !positions.has(edge.target)) continue
    adjacency.set(edge.source, [...(adjacency.get(edge.source) ?? []), edge.target])
    adjacency.set(edge.target, [...(adjacency.get(edge.target) ?? []), edge.source])
  }

  const repulsion = 8000
  const springLength = 90
  const springStrength = 0.04
  const damping = 0.85

  for (let step = 0; step < iterations; step += 1) {
    const forces = new Map<string, { x: number; y: number }>(ids.map((id) => [id, { x: 0, y: 0 }]))

    // 斥力（两两）
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const a = positions.get(ids[i])!
        const b = positions.get(ids[j])!
        let dx = a.x - b.x
        let dy = a.y - b.y
        let distSq = dx * dx + dy * dy
        if (distSq < 1) {
          dx = (Math.random() - 0.5) * 2
          dy = (Math.random() - 0.5) * 2
          distSq = dx * dx + dy * dy + 0.01
        }
        const dist = Math.sqrt(distSq)
        const force = repulsion / distSq
        const fa = forces.get(ids[i])!
        const fb = forces.get(ids[j])!
        fa.x += (dx / dist) * force
        fa.y += (dy / dist) * force
        fb.x -= (dx / dist) * force
        fb.y -= (dy / dist) * force
      }
    }

    // 引力（边）
    for (const edge of edges) {
      const a = positions.get(edge.source)
      const b = positions.get(edge.target)
      if (!a || !b) continue
      const dx = b.x - a.x
      const dy = b.y - a.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
      const force = springStrength * (dist - springLength)
      const fa = forces.get(edge.source)!
      const fb = forces.get(edge.target)!
      fa.x += (dx / dist) * force
      fa.y += (dy / dist) * force
      fb.x -= (dx / dist) * force
      fb.y -= (dy / dist) * force
    }

    // 应用位移并限制在画布内
    for (const id of ids) {
      const pos = positions.get(id)!
      const force = forces.get(id)!
      pos.x = Math.max(24, Math.min(width - 24, pos.x + force.x * damping))
      pos.y = Math.max(24, Math.min(height - 24, pos.y + force.y * damping))
    }
  }

  return { nodes: positions, width, height }
}
