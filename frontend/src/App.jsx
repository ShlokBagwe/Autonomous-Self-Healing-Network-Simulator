import { useState, useEffect, useCallback } from 'react'
import { fetchTopology } from './api/client'
import { useEventStream } from './hooks/useEventStream'

import TopologyGraph   from './components/TopologyGraph'
import FaultInjector   from './components/FaultInjector'
import MetricsPanel    from './components/MetricsPanel'
import AlertFeed       from './components/AlertFeed'
import RerouteLog      from './components/RerouteLog'
import FeatureImportance from './components/FeatureImportance'

export default function App() {
  const { alerts, reroutes, telemetry, wsStatus, clearAll } = useEventStream()
  const [topology, setTopology] = useState(null)
  const [selectedElement, setSelectedElement] = useState(null) // { id, type }
  const [selectedSet, setSelectedSet] = useState(new Set())
  const [activeTab, setActiveTab] = useState('alerts')         // 'alerts' | 'reroutes' | 'xai'

  // ── Fetch topology periodically ──
  const loadTopology = useCallback(() => {
    fetchTopology().then(setTopology).catch(console.error)
  }, [])

  useEffect(() => {
    loadTopology()
    const iv = setInterval(loadTopology, 3000)
    return () => clearInterval(iv)
  }, [loadTopology])

  // ── Topology node/edge click handler ──
  const handleSelect = useCallback((id, type) => {
    setSelectedElement({ id, type })
    setSelectedSet(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleFaultInjected = useCallback(() => {
    setTimeout(loadTopology, 200)
    setSelectedElement(null)
    setSelectedSet(new Set())
  }, [loadTopology])

  const handleReset = useCallback(() => {
    clearAll()
    setTimeout(loadTopology, 200)
    setSelectedElement(null)
    setSelectedSet(new Set())
  }, [clearAll, loadTopology])

  return (
    <div className="min-h-screen bg-[#07090e] text-slate-100 flex flex-col"
      style={{ backgroundImage: 'radial-gradient(circle at 12% 12%, rgba(56,189,248,0.06) 0%, transparent 40%), radial-gradient(circle at 88% 88%, rgba(129,140,248,0.06) 0%, transparent 40%)' }}>

      {/* ── Header ── */}
      <header className="sticky top-0 z-50 flex items-center justify-between px-6 py-3 border-b border-white/[0.06] bg-[#07090e]/80 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg font-black shadow-lg"
            style={{ background: 'linear-gradient(135deg, #0284c7, #6366f1)', boxShadow: '0 0 20px rgba(56,189,248,0.3)' }}>
            ⚡
          </div>
          <div>
            <h1 className="text-[15px] font-bold tracking-tight text-slate-100">Autonomous Self-Healing Network Simulator</h1>
            <p className="text-[11px] text-slate-500">SNMP Telemetry · ML Engine · Dynamic Dijkstra Controller · Fault Reconciliation</p>
          </div>
        </div>

        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold ${
          wsStatus === 'connected'
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
            : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
        }`}>
          <span className={`w-2 h-2 rounded-full ${wsStatus === 'connected' ? 'bg-emerald-400 pulse-dot' : 'bg-amber-400'}`} />
          {wsStatus === 'connected' ? 'Live WebSocket' : 'Reconnecting…'}
        </div>
      </header>

      {/* ── Main Content ── */}
      <main className="flex-1 grid grid-cols-[1fr_380px] gap-5 p-5 max-w-[1600px] mx-auto w-full">

        {/* ── Left column: Topology + Metrics + Tabbed panels ── */}
        <div className="flex flex-col gap-5">

          {/* Topology Card */}
          <div className="rounded-2xl border border-white/[0.07] bg-slate-900/50 backdrop-blur-sm p-4"
            style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">
                🌐 Live Network Topology
              </h2>
              {topology && (
                <span className="text-[10px] text-slate-600 mono">
                  {topology.nodes?.length ?? 0} nodes · {topology.edges?.length ?? 0} links
                </span>
              )}
            </div>

            <div className="rounded-xl overflow-hidden border border-white/[0.05]"
              style={{ height: 420, background: 'radial-gradient(circle at center, rgba(30,41,59,0.5) 0%, rgba(7,9,14,0.7) 100%)' }}>
              <TopologyGraph
                topology={topology}
                alerts={alerts}
                reroutes={reroutes}
                telemetry={telemetry}
                onSelect={handleSelect}
                selected={selectedSet}
              />
            </div>

            <p className="mt-2 text-[10px] text-slate-600 text-center">
              Click any node (◉) or edge (⟵⟶) to select it for fault injection · Cyan path = active Dijkstra route
            </p>
          </div>

          {/* Metrics */}
          <div className="rounded-2xl border border-white/[0.07] bg-slate-900/50 backdrop-blur-sm p-4">
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">
              📊 Live Metrics
            </h2>
            <MetricsPanel telemetry={telemetry} alerts={alerts} reroutes={reroutes} />
          </div>

          {/* Tabbed: Alerts · Reroutes · XAI */}
          <div className="rounded-2xl border border-white/[0.07] bg-slate-900/50 backdrop-blur-sm p-4 flex-1">
            {/* Tab buttons */}
            <div className="flex gap-1 mb-4 p-1 bg-white/[0.03] rounded-lg w-fit">
              {[
                { key: 'alerts',   label: `📡 Alerts (${alerts.length})` },
                { key: 'reroutes', label: `🔄 Reroutes (${reroutes.length})` },
                { key: 'xai',      label: '🧠 Feature Importance' },
              ].map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all duration-150 ${
                    activeTab === tab.key
                      ? 'bg-slate-700 text-slate-100 shadow'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {activeTab === 'alerts'   && <AlertFeed alerts={alerts} />}
            {activeTab === 'reroutes' && <RerouteLog reroutes={reroutes} />}
            {activeTab === 'xai'      && <FeatureImportance />}
          </div>
        </div>

        {/* ── Right column: Fault Injector ── */}
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl border border-white/[0.07] bg-slate-900/50 backdrop-blur-sm p-4 sticky top-24"
            style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}>
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">
              ⚡ Fault Injector
            </h2>
            <FaultInjector
              onFaultInjected={handleFaultInjected}
              onReset={handleReset}
              selectedElement={selectedElement}
            />
          </div>

          {/* Quick stats sidebar */}
          <div className="rounded-2xl border border-white/[0.07] bg-slate-900/50 backdrop-blur-sm p-4">
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">
              📈 Session Summary
            </h2>
            <div className="flex flex-col gap-2 text-xs text-slate-400">
              <div className="flex justify-between">
                <span>Total alerts raised</span>
                <span className="mono text-slate-200 font-semibold">{alerts.length}</span>
              </div>
              <div className="flex justify-between">
                <span>— SNMP TRAP</span>
                <span className="mono text-rose-400">{alerts.filter(a=>a.source==='snmp_trap').length}</span>
              </div>
              <div className="flex justify-between">
                <span>— ML Engine</span>
                <span className="mono text-indigo-400">{alerts.filter(a=>a.source==='ml_engine').length}</span>
              </div>
              <div className="flex justify-between mt-1">
                <span>Reroute events</span>
                <span className="mono text-sky-400 font-semibold">{reroutes.length}</span>
              </div>
              <div className="flex justify-between">
                <span>Links monitored</span>
                <span className="mono text-slate-200">{telemetry.size}</span>
              </div>
              <div className="h-px bg-white/[0.06] my-1" />
              <button
                onClick={() => { clearAll(); loadTopology() }}
                className="text-[10px] text-slate-600 hover:text-slate-400 text-left transition-colors"
              >
                Clear session history
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
