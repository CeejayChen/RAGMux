import { describe, expect, it } from 'vitest'
import { computeLayout } from '../src/components/graphLayout'

describe('computeLayout', () => {
  it('为每个节点产出画布内的坐标', () => {
    const nodes = ['a', 'b', 'c', 'd']
    const edges = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }]
    const layout = computeLayout(nodes, edges, 800, 600, 80)
    expect(layout.nodes.size).toBe(4)
    for (const pos of layout.nodes.values()) {
      expect(pos.x).toBeGreaterThanOrEqual(24)
      expect(pos.x).toBeLessThanOrEqual(800 - 24)
      expect(pos.y).toBeGreaterThanOrEqual(24)
      expect(pos.y).toBeLessThanOrEqual(600 - 24)
    }
  })

  it('相连节点应比随机分布更接近（弹簧引力）', () => {
    const layout = computeLayout(['a', 'b'], [{ source: 'a', target: 'b' }], 800, 600, 300)
    const a = layout.nodes.get('a')!
    const b = layout.nodes.get('b')!
    const dist = Math.hypot(a.x - b.x, a.y - b.y)
    expect(dist).toBeLessThan(400) // 远小于初始圆分布的直径
  })

  it('空节点返回空布局', () => {
    expect(computeLayout([], [], 800, 600).nodes.size).toBe(0)
  })
})
