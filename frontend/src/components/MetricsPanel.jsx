/**
 * MetricsPanel — derived statistics from live telemetry + alert stream.
 *
 * Props:
 *   telemetry  — Map<link, TelemetryReading>
 *   alerts     — Alert[]
 *   reroutes   — RerouteEvent[]
 */
export default function MetricsPanel({ telemetry, alerts, reroutes }) {
  const readings = Array.from(telemetry?.values() ?? [])

  // Average latency across operational links carrying traffic
  // Failed links (packet_loss >= 100) have no valid round-trip transmissions and are excluded from RTT averaging
  const operationalReadings = readings.filter(r => r && r.packet_loss < 100 && r.latency < 1000)
  const avgLatency = operationalReadings.length
    ? (operationalReadings.reduce((s, r) => s + r.latency, 0) / operationalReadings.length).toFixed(1)
    : '—'

  // PDR proxy: proportion of links with packet_loss = 0
  const healthyLinks = readings.filter(r => r.packet_loss < 1).length
  const pdr = readings.length
    ? `${((healthyLinks / readings.length) * 100).toFixed(0)}%`
    : '—'

  // TRAP vs ML agreement rate from reconciliation data
  const trapAlerts = alerts.filter(a => a.source === 'snmp_trap').length
  const mlAlerts   = alerts.filter(a => a.source === 'ml_engine').length
  const totalAlerts = trapAlerts + mlAlerts
  const agreementRate = totalAlerts > 0
    ? `${Math.min(100, Math.round((Math.min(trapAlerts, mlAlerts) / Math.max(trapAlerts, mlAlerts, 1)) * 100))}%`
    : '—'

  // Mean MTTR from reroute events
  const mttrs = reroutes.map(r => r.recovery_latency_ms).filter(v => v != null)
  const meanMttr = mttrs.length
    ? `${(mttrs.reduce((a, b) => a + b, 0) / mttrs.length).toFixed(0)} ms`
    : '—'

  // Avg utilization
  const avgUtil = readings.length
    ? `${(readings.reduce((s, r) => s + r.utilization * 100, 0) / readings.length).toFixed(0)}%`
    : '—'

  // Avg jitter
  const avgJitter = readings.length
    ? `${(readings.reduce((s, r) => s + r.jitter, 0) / readings.length).toFixed(1)} ms`
    : '—'

  const metrics = [
    { label: 'Avg RTT Latency',    value: `${avgLatency} ms`, color: 'text-sky-400',     id: 'metric-latency' },
    { label: 'Packet Delivery',    value: pdr,                color: 'text-emerald-400', id: 'metric-pdr'     },
    { label: 'TRAP/ML Agreement',  value: agreementRate,      color: 'text-indigo-400',  id: 'metric-agree'   },
    { label: 'Mean MTTR',          value: meanMttr,           color: 'text-amber-400',   id: 'metric-mttr'    },
    { label: 'Avg Utilization',    value: avgUtil,            color: 'text-sky-300',     id: 'metric-util'    },
    { label: 'Avg Jitter',         value: avgJitter,          color: 'text-purple-400',  id: 'metric-jitter'  },
  ]

  return (
    <div className="grid grid-cols-3 gap-3">
      {metrics.map(m => (
        <div
          key={m.id}
          id={m.id}
          className="bg-white/[0.025] border border-white/[0.06] rounded-xl p-3"
        >
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{m.label}</p>
          <p className={`mono text-lg font-bold leading-tight ${m.color}`}>{m.value}</p>
        </div>
      ))}
    </div>
  )
}
