/**
 * AlertFeed — source-tagged (TRAP vs ML) live alert list.
 *
 * Props:
 *   alerts — Alert[] (newest first)
 */
export default function AlertFeed({ alerts }) {
  if (!alerts.length) {
    return (
      <p className="text-xs text-slate-600 text-center py-8">
        No alerts yet — network operating normally.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-2 overflow-y-auto max-h-64 pr-1">
      {alerts.map((alert) => {
        const isTrap = alert.source === 'snmp_trap'
        const state   = alert.predicted_state
        const stateColor =
          state === 'failed'    ? 'text-rose-400'   :
          state === 'congested' ? 'text-amber-400'  :
                                  'text-emerald-400'

        return (
          <div
            key={alert._id}
            className={`
              feed-item-enter
              flex flex-col gap-1 rounded-r-lg border-l-2 px-3 py-2 text-xs
              bg-slate-900/60
              ${isTrap
                ? 'border-rose-500/70'
                : 'border-indigo-500/70'
              }
            `}
          >
            <div className="flex items-center justify-between">
              <span
                className={`
                  inline-block px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide
                  ${isTrap
                    ? 'bg-rose-500/15 text-rose-300'
                    : 'bg-indigo-500/15 text-indigo-300'
                  }
                `}
              >
                {isTrap ? 'SNMP TRAP' : 'ML Engine'}
              </span>
              <span className="text-slate-600 mono text-[10px]">
                t={alert.timestamp?.toFixed?.(2) ?? '—'}
              </span>
            </div>

            <div className="flex items-baseline gap-1.5">
              <span className="font-semibold text-slate-200 mono">{alert.link}</span>
              <span className="text-slate-500">→</span>
              <span className={`font-semibold uppercase text-[11px] ${stateColor}`}>{state}</span>
              {alert.confidence != null && (
                <span className="text-slate-500 ml-auto">
                  {(alert.confidence * 100).toFixed(1)}%
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
