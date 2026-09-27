/**
 * RerouteLog — scrollable history of RerouteEvents received from the WebSocket stream.
 *
 * Props:
 *   reroutes — RerouteEvent[] (newest first)
 */
export default function RerouteLog({ reroutes }) {
  if (!reroutes.length) {
    return (
      <p className="text-xs text-slate-600 text-center py-8">
        Primary routes intact — no rerouting events yet.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-2 overflow-y-auto max-h-64 pr-1">
      {reroutes.map((ev) => {
        const oldPath = ev.old_path?.join(' → ') || '—'
        const hasNewPath = ev.new_path && ev.new_path.length > 1
        const newPath = hasNewPath
          ? ev.new_path.join(' → ')
          : 'None (No surviving path — Destination Unreachable)'
        const mttr = ev.recovery_latency_ms != null
          ? `${ev.recovery_latency_ms.toFixed(1)} ms`
          : '—'
        const triggerSrc = ev.trigger_alert?.source ?? '—'
        const isTrap = triggerSrc === 'snmp_trap'

        return (
          <div
            key={ev._id}
            className={`feed-item-enter border-l-2 rounded-r-lg px-3 py-2 text-xs flex flex-col gap-1.5 ${
              hasNewPath
                ? 'border-sky-500/60 bg-slate-900/60'
                : 'border-rose-500/80 bg-rose-950/25'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${
                hasNewPath
                  ? 'bg-sky-500/15 text-sky-300'
                  : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
              }`}>
                {hasNewPath ? 'Dijkstra Reroute' : 'Route Severed · Unreachable'}
              </span>
              <span className="text-emerald-400 font-semibold mono text-[11px]">MTTR {mttr}</span>
            </div>

            <div className="flex flex-col gap-0.5">
              <div className="flex items-baseline gap-1.5">
                <span className="text-slate-500 w-12 shrink-0">From:</span>
                <span className="mono text-slate-400 line-through text-[11px]">{oldPath}</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-slate-500 w-12 shrink-0">To:</span>
                <span className={`mono font-semibold text-[11px] ${
                  hasNewPath ? 'text-sky-400' : 'text-rose-400'
                }`}>
                  {newPath}
                </span>
              </div>
            </div>

            <div className="flex gap-2 text-[10px] text-slate-600">
              <span>Failed: <span className="text-rose-400 mono">{ev.failed_link}</span></span>
              <span>·</span>
              <span>Trigger: <span className={isTrap ? 'text-rose-400' : 'text-indigo-400'}>{isTrap ? 'TRAP' : 'ML'}</span></span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
