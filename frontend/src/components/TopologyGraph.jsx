import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * TopologyGraph — renders whatever GET /api/topology returns.
 *
 * Props:
 *   topology  — { nodes: [{id, status}], edges: [{source, target, link, ...}], active_paths }
 *   alerts    — latest alerts array (used to highlight faulted elements)
 *   reroutes  — latest reroutes array (used to highlight new active paths)
 *   onSelect  — (elementId: string, type: 'node'|'edge') => void  (for FaultInjector)
 *   selected  — currently selected element ids (Set)
 */
export default function TopologyGraph({ topology, alerts, reroutes, telemetry, onSelect, selected }) {
  const svgRef = useRef(null)
  const [layout, setLayout] = useState({ nodes: {}, edges: [] })

  // ── Compute auto-layout: place nodes in a circle + resolve edge coords ──
  useEffect(() => {
    if (!topology?.nodes?.length) return

    const nodes = topology.nodes
    const n = nodes.length
    const cx = 400
    const cy = 240
    const r = Math.min(160, 50 + n * 14)

    const positions = {}
    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2
      positions[node.id] = {
        x: Math.round(cx + r * Math.cos(angle)),
        y: Math.round(cy + r * Math.sin(angle)),
      }
    })

    setLayout({ positions, edges: topology.edges || [] })
  }, [topology])

  // ── Determine which elements are faulted vs congested based on latest alerts ──
  const faultedLinks = new Set()
  const faultedNodes = new Set()
  const congestedLinks = new Set()

  alerts.slice(0, 10).forEach((a) => {
    const link = a.link || ''
    const isHardFail = a.source === 'snmp_trap' || a.predicted_state === 'failed'
    const isCongestion = a.predicted_state === 'congested' || a.predicted_state === 'degrading'

    if (link.includes('-')) {
      if (isHardFail) {
        faultedLinks.add(link)
        faultedLinks.add(link.split('-').reverse().join('-'))
      } else if (isCongestion) {
        congestedLinks.add(link)
        congestedLinks.add(link.split('-').reverse().join('-'))
      }
    } else {
      if (isHardFail) {
        faultedNodes.add(link)
      }
    }
  })

  // Helper predicates for failed nodes and links
  const isNodeDown = (nodeId) => {
    const nodeObj = topology?.nodes?.find(n => n.id === nodeId)
    return nodeObj?.status === 'down' || faultedNodes.has(nodeId)
  }

  const isEdgeFailed = (u, v) => {
    const linkFwd = `${u}-${v}`
    const linkBwd = `${v}-${u}`
    const edgeObj = topology?.edges?.find(e => (e.source === u && e.target === v) || (e.source === v && e.target === u))
    return (
      edgeObj?.status === 'failed' ||
      edgeObj?.ifOperStatus === 2 ||
      (edgeObj?.packet_loss != null && edgeObj.packet_loss >= 100.0) ||
      faultedLinks.has(linkFwd) ||
      faultedLinks.has(linkBwd)
    )
  }

  // ── Determine active path from latest reroute or topology ──
  let candidatePath = []
  if (reroutes?.length > 0) {
    candidatePath = (reroutes[0]?.new_path && reroutes[0].new_path.length > 1)
      ? reroutes[0].new_path
      : []
  } else if (topology?.active_paths) {
    const topoPath = Object.values(topology.active_paths)[0]
    candidatePath = Array.isArray(topoPath) ? topoPath : []
  }

  // Verify candidate path viability:
  // An active path must have >1 nodes, every node must be up, and every edge must be operational.
  let isPathViable = candidatePath.length > 1
  if (isPathViable) {
    for (let i = 0; i < candidatePath.length; i++) {
      if (isNodeDown(candidatePath[i])) {
        isPathViable = false
        break
      }
      if (i < candidatePath.length - 1) {
        if (isEdgeFailed(candidatePath[i], candidatePath[i + 1])) {
          isPathViable = false
          break
        }
      }
    }
  }

  const activePathNodes = isPathViable ? candidatePath : []

  const activePathSet = new Set() // set of "U|V" pairs
  if (activePathNodes.length > 1) {
    for (let i = 0; i < activePathNodes.length - 1; i++) {
      activePathSet.add(`${activePathNodes[i]}|${activePathNodes[i + 1]}`)
      activePathSet.add(`${activePathNodes[i + 1]}|${activePathNodes[i]}`)
    }
  }

  if (!topology?.nodes?.length || !layout.positions) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        Loading topology…
      </div>
    )
  }

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 800 480"
      className="w-full h-full"
      aria-label="Network Topology Graph"
    >
      <defs>
        <filter id="glow-cyan" filterUnits="userSpaceOnUse" x="0" y="0" width="800" height="480">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="glow-red" filterUnits="userSpaceOnUse" x="0" y="0" width="800" height="480">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="glow-amber" filterUnits="userSpaceOnUse" x="0" y="0" width="800" height="480">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="#38bdf8" opacity="0.6" />
        </marker>
      </defs>

      {/* ── Edges ── */}
      {(layout.edges || []).map((edge) => {
        const p1 = layout.positions[edge.source]
        const p2 = layout.positions[edge.target]
        if (!p1 || !p2) return null

        const linkFwd = `${edge.source}-${edge.target}`
        const linkBwd = `${edge.target}-${edge.source}`
        const isFaulted = isEdgeFailed(edge.source, edge.target)
        const isCongested =
          congestedLinks.has(linkFwd) ||
          congestedLinks.has(linkBwd) ||
          edge.status === 'congested' ||
          edge.status === 'degrading'
        const isActive =
          activePathSet.has(`${edge.source}|${edge.target}`) ||
          activePathSet.has(`${edge.target}|${edge.source}`)
        const isSelected =
          selected?.has(linkFwd) || selected?.has(linkBwd)

        let stroke = '#1e293b'
        let strokeWidth = 2
        let filter = ''
        let extraClass = ''

        if (isFaulted) {
          stroke = '#f43f5e'
          strokeWidth = 3
          extraClass = 'edge-fault'
          filter = 'url(#glow-red)'
        } else if (isActive && isCongested) {
          stroke = '#f59e0b'
          strokeWidth = 4
          filter = 'url(#glow-amber)'
        } else if (isActive) {
          stroke = '#38bdf8'
          strokeWidth = 4
          filter = 'url(#glow-cyan)'
        } else if (isCongested) {
          stroke = '#f59e0b'
          strokeWidth = 3
        } else if (isSelected) {
          stroke = '#818cf8'
          strokeWidth = 3
        }

        // Edge label (latency) — prefer live telemetry reading if available, fallback to edge.latency
        const liveReading = telemetry?.get?.(linkFwd) || telemetry?.get?.(linkBwd)
        const currentLatency = liveReading?.latency ?? edge.latency
        const midX = Math.round((p1.x + p2.x) / 2)
        const midY = Math.round((p1.y + p2.y) / 2)

        return (
          <g key={`${edge.source}-${edge.target}`}>
            <line
              x1={p1.x} y1={p1.y}
              x2={p2.x} y2={p2.y}
              stroke={stroke}
              strokeWidth={strokeWidth}
              strokeDasharray={isFaulted ? '6,3' : 'none'}
              filter={filter}
              className={`cursor-pointer transition-all duration-300 ${extraClass}`}
              onClick={() => onSelect?.(`${edge.source}-${edge.target}`, 'edge')}
            />
            {/* Clickable invisible wider hit area */}
            <line
              x1={p1.x} y1={p1.y}
              x2={p2.x} y2={p2.y}
              stroke="transparent"
              strokeWidth={14}
              className="cursor-pointer"
              onClick={() => onSelect?.(`${edge.source}-${edge.target}`, 'edge')}
            />
            {isActive && (
              <text
                x={midX}
                y={midY - 6}
                textAnchor="middle"
                fill={isFaulted ? '#f43f5e' : (isCongested ? '#f59e0b' : '#38bdf8')}
                fontSize="9"
                opacity="0.85"
                fontWeight={isCongested ? '700' : '400'}
              >
                {isFaulted
                  ? 'FAILED'
                  : (currentLatency != null && currentLatency < 1000
                      ? `${Number(currentLatency).toFixed(1)}ms`
                      : '')}
              </text>
            )}
          </g>
        )
      })}

      {/* ── Nodes ── */}
      {(topology.nodes || []).map((node) => {
        const pos = layout.positions[node.id]
        if (!pos) return null

        const isFaulted = faultedNodes.has(node.id) || node.status === 'down'
        const isInActivePath = activePathNodes.includes(node.id)
        const isSelected = selected?.has(node.id)
        const radius = isInActivePath ? 20 : 15

        let fill = '#0f172a'
        let stroke = '#334155'
        let strokeWidth = 2
        let filter = ''
        let textFill = '#94a3b8'

        if (isFaulted) {
          fill = 'rgba(244,63,94,0.2)'
          stroke = '#f43f5e'
          strokeWidth = 3
          filter = 'url(#glow-red)'
          textFill = '#fca5a5'
        } else if (isSelected) {
          fill = 'rgba(129,140,248,0.2)'
          stroke = '#818cf8'
          strokeWidth = 3
          textFill = '#c7d2fe'
        } else if (isInActivePath) {
          fill = 'rgba(2,132,199,0.3)'
          stroke = '#38bdf8'
          strokeWidth = 3
          filter = 'url(#glow-cyan)'
          textFill = '#f0f9ff'
        }

        return (
          <g
            key={node.id}
            className={`cursor-pointer transition-all duration-300 ${isInActivePath ? 'node-active' : ''}`}
            onClick={() => onSelect?.(node.id, 'node')}
          >
            <circle
              cx={pos.x}
              cy={pos.y}
              r={radius}
              fill={fill}
              stroke={stroke}
              strokeWidth={strokeWidth}
              filter={filter}
              className="transition-all duration-300"
            />
            <text
              x={pos.x}
              y={pos.y + 1}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={textFill}
              fontSize="13"
              fontWeight="700"
              fontFamily="var(--font-sans)"
            >
              {node.id}
            </text>
            {/* Node status indicator dot */}
            {(isFaulted || isSelected) && (
              <circle cx={pos.x + radius - 3} cy={pos.y - radius + 3} r="4"
                fill={isFaulted ? '#f43f5e' : '#818cf8'} />
            )}
          </g>
        )
      })}

      {/* ── Active path label ── */}
      {activePathNodes.length > 1 ? (
        <text x="8" y="470" fill="#38bdf8" fontSize="11" opacity="0.85" fontFamily="var(--font-mono)">
          Active Path: {activePathNodes.join(' → ')}
        </text>
      ) : (
        <text x="8" y="470" fill="#f43f5e" fontSize="11" opacity="0.9" fontFamily="var(--font-mono)" fontWeight="600">
          ⚠️ Route Severed: No Surviving Path Available (Destination Unreachable)
        </text>
      )}
    </svg>
  )
}
