import { useRef, useEffect, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const STATUS_COLOR = {
  up: '#00ff88',
  down: '#ff4444',
  degraded: '#ffaa00',
  unknown: '#4a5568',
}

export default function TopologyGraph({ graph, height = 500 }) {
  const fgRef = useRef()

  const { nodes = [], edges = [] } = graph || {}

  const graphData = {
    nodes: nodes.map((n) => ({ ...n, color: STATUS_COLOR[n.status] || '#4a5568' })),
    links: edges.map((e) => ({ source: e.source, target: e.target })),
  }

  useEffect(() => {
    if (fgRef.current) {
      setTimeout(() => fgRef.current.zoomToFit(400, 40), 500)
    }
  }, [graph])

  const paintNode = useCallback((node, ctx, globalScale) => {
    const size = node.is_gateway ? 10 : 6
    const color = node.color || '#4a5568'

    // Glow
    ctx.shadowColor = color
    ctx.shadowBlur = 12
    ctx.beginPath()
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
    ctx.shadowBlur = 0

    // Ring for gateway
    if (node.is_gateway) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI)
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.stroke()
    }

    // Label
    const label = node.label || node.ip
    const fontSize = Math.max(10 / globalScale, 2)
    ctx.font = `${fontSize}px monospace`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = '#e2e8f0'
    ctx.fillText(label, node.x, node.y + size + 2)
  }, [])

  if (!graph) return (
    <div className="flex items-center justify-center h-64 text-gray-500 text-sm">
      No topology data
    </div>
  )

  return (
    <div style={{ background: '#0a0e1a', borderRadius: 8, overflow: 'hidden' }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        width={undefined}
        height={height}
        backgroundColor="#0a0e1a"
        nodeCanvasObject={paintNode}
        nodeCanvasObjectMode={() => 'replace'}
        linkColor={() => '#1e2d4a'}
        linkWidth={1}
        nodeRelSize={6}
        enableZoomInteraction
        enablePanInteraction
        cooldownTicks={100}
        nodeLabel={(n) => `${n.label || n.ip}${n.mac ? `\nMAC: ${n.mac}` : ''}\nStatus: ${n.status}`}
      />
    </div>
  )
}
