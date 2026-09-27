import { useState, useEffect } from 'react'
import { fetchTopology, postFault, postReset } from '../api/client'

const FAULT_KINDS = [
  { value: 'link_failure',  label: 'Link Failure',          forEdge: true,  forNode: false, multiTarget: false },
  { value: 'router_crash',  label: 'Router Crash',          forEdge: false, forNode: true,  multiTarget: false },
  { value: 'congestion',    label: 'Congestion',            forEdge: true,  forNode: false, multiTarget: false },
  { value: 'degradation',   label: 'Progressive Degradation',forEdge: true, forNode: false, multiTarget: false },
  { value: 'multi_fault',   label: 'Multi-Fault',           forEdge: true,  forNode: true,  multiTarget: true  },
]

/**
 * FaultInjector — dynamic target + fault type selector.
 *
 * Props:
 *   onFaultInjected  — () => void, called after successful POST /api/fault
 *   onReset          — () => void, called after successful POST /api/reset
 *   selectedElement  — { id: string, type: 'node'|'edge' } from TopologyGraph click
 */
export default function FaultInjector({ onFaultInjected, onReset, selectedElement }) {
  const [topology, setTopology] = useState(null)
  const [kind, setKind] = useState('link_failure')
  const [targets, setTargets] = useState([])   // array for multi_fault support
  const [status, setStatus] = useState(null)   // 'injecting' | 'ok' | 'error'

  // Refresh target options from live topology
  useEffect(() => {
    fetchTopology().then(setTopology).catch(console.error)
  }, [])

  // Auto-populate target when user clicks a node/edge on the topology graph
  useEffect(() => {
    if (!selectedElement) return
    const { id, type } = selectedElement
    const currentKind = FAULT_KINDS.find(k => k.value === kind)
    if (!currentKind) return

    const faultSupportsSelection =
      (type === 'node' && currentKind.forNode) ||
      (type === 'edge' && currentKind.forEdge)

    if (!faultSupportsSelection) return

    if (currentKind.multiTarget) {
      setTargets(prev => prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id])
    } else {
      setTargets([id])
    }
  }, [selectedElement])

  // When kind changes, reset targets if incompatible
  useEffect(() => {
    setTargets([])
  }, [kind])

  const currentKind = FAULT_KINDS.find(k => k.value === kind)

  // Build target options based on selected fault kind
  const nodeOptions = (topology?.nodes || []).map(n => ({ value: n.id, label: `Node ${n.id}`, type: 'node' }))
  const edgeOptions = (topology?.edges || []).map(e => ({ value: `${e.source}-${e.target}`, label: `Link ${e.source}–${e.target}`, type: 'edge' }))

  let targetOptions = []
  if (currentKind?.forEdge && currentKind?.forNode) targetOptions = [...nodeOptions, ...edgeOptions]
  else if (currentKind?.forEdge) targetOptions = edgeOptions
  else if (currentKind?.forNode) targetOptions = nodeOptions

  const toggleTarget = (val) => {
    if (currentKind?.multiTarget) {
      setTargets(prev => prev.includes(val) ? prev.filter(t => t !== val) : [...prev, val])
    } else {
      setTargets([val])
    }
  }

  const handleInject = async () => {
    if (!targets.length) return
    setStatus('injecting')
    try {
      const target = currentKind?.multiTarget ? targets : targets[0]
      await postFault(kind, target)
      setStatus('ok')
      onFaultInjected?.()
      setTimeout(() => setStatus(null), 2500)
    } catch (e) {
      setStatus('error')
      setTimeout(() => setStatus(null), 3000)
    }
  }

  const handleReset = async () => {
    setStatus('injecting')
    try {
      await postReset()
      setTargets([])
      setStatus('ok')
      onReset?.()
      setTimeout(() => setStatus(null), 2000)
    } catch (e) {
      setStatus('error')
      setTimeout(() => setStatus(null), 3000)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Tip about click-to-select */}
      <p className="text-xs text-slate-500 leading-relaxed">
        Click any node or edge in the topology to auto-select it, or choose from the dropdowns below.
      </p>

      {/* Fault Type Selector */}
      <div>
        <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">
          Fault Type
        </label>
        <select
          value={kind}
          onChange={e => setKind(e.target.value)}
          className="w-full bg-slate-800/60 border border-white/10 text-slate-100 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-sky-500/60 focus:ring-1 focus:ring-sky-500/30"
        >
          {FAULT_KINDS.map(k => (
            <option key={k.value} value={k.value}>{k.label}</option>
          ))}
        </select>
      </div>

      {/* Target Selector */}
      <div>
        <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">
          Target{currentKind?.multiTarget ? 's (select multiple)' : ''}
          {targets.length > 0 && (
            <span className="ml-2 text-sky-400 normal-case font-medium">
              {targets.join(', ')}
            </span>
          )}
        </label>
        <div className="flex flex-col gap-1 max-h-44 overflow-y-auto pr-1">
          {targetOptions.length === 0 && (
            <p className="text-xs text-slate-600 py-1">Loading…</p>
          )}
          {targetOptions.map(opt => {
            const active = targets.includes(opt.value)
            return (
              <button
                key={opt.value}
                onClick={() => toggleTarget(opt.value)}
                className={`
                  w-full text-left px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150
                  ${active
                    ? 'bg-sky-500/20 border border-sky-500/50 text-sky-300'
                    : 'bg-white/[0.03] border border-white/[0.06] text-slate-400 hover:bg-white/[0.06] hover:text-slate-200'
                  }
                `}
              >
                <span className={`mr-1.5 ${opt.type === 'edge' ? 'opacity-60' : ''}`}>
                  {opt.type === 'node' ? '◉' : '⟵⟶'}
                </span>
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Status feedback */}
      {status === 'ok' && (
        <p className="text-xs text-emerald-400 font-medium">✓ Command sent successfully</p>
      )}
      {status === 'error' && (
        <p className="text-xs text-rose-400 font-medium">✗ Request failed — is the bridge server running?</p>
      )}

      {/* Action buttons */}
      <div className="flex flex-col gap-2">
        <button
          id="inject-btn"
          onClick={handleInject}
          disabled={!targets.length || status === 'injecting'}
          className={`
            w-full py-2.5 px-4 rounded-lg text-sm font-semibold transition-all duration-200
            ${targets.length && status !== 'injecting'
              ? 'bg-rose-500/20 border border-rose-500/40 text-rose-300 hover:bg-rose-500/30 hover:border-rose-500/70'
              : 'bg-white/[0.03] border border-white/[0.06] text-slate-600 cursor-not-allowed'
            }
          `}
        >
          {status === 'injecting' ? '⚡ Injecting…' : `⚡ Inject ${FAULT_KINDS.find(k=>k.value===kind)?.label ?? ''}`}
        </button>

        <button
          id="reset-btn"
          onClick={handleReset}
          disabled={status === 'injecting'}
          className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/60 transition-all duration-200"
        >
          ↺ Restore Network State
        </button>
      </div>
    </div>
  )
}
