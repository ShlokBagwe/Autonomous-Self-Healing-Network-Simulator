/**
 * MetricsPanel — derived statistics from live telemetry + alert stream.
 *
 * Props:
 *   telemetry  — Map<link, TelemetryReading>
 *   alerts     — Alert[]
 *   reroutes   — RerouteEvent[]
 */
export default function MetricsPanel({ telemetry, alerts, reroutes, metricsSummary }) {
  const readings = Array.from(telemetry?.values() ?? [])

  // Standardized Avg RTT Latency:
  // Strictly derived from backend metricsSummary as the single source of truth.
  // Displays '—' until the backend metric arrives, preventing any partial or collapsed local averaging.
  const avgLatency = metricsSummary?.avg_rtt_latency != null
    ? `${metricsSummary.avg_rtt_latency.toFixed(1)} ms`
    : '—'

  // PDR proxy: proportion of links with packet_loss = 0
  const healthyLinks = readings.filter(r => r.packet_loss < 1).length
  const pdr = readings.length
    ? `${((healthyLinks / readings.length) * 100).toFixed(0)}%`
    : '—'

  // Standardized TRAP/ML Agreement Rate:
  // Strictly derived from backend metricsSummary as the single source of truth.
  // Displays '—' until alerts/reconciliation records exist.
  const agreementRate = metricsSummary?.agreement_rate != null
    ? `${(metricsSummary.agreement_rate * 100).toFixed(0)}%`
    : '—'

  // Split MTTR: Reactive (SNMP TRAP-triggered) vs Proactive (ML Engine-triggered)
  const reactiveMttrs = reroutes
    .filter(r => r.trigger_alert?.source === 'snmp_trap' && r.recovery_latency_ms != null)
    .map(r => r.recovery_latency_ms)
  const proactiveMttrs = reroutes
    .filter(r => r.trigger_alert?.source === 'ml_engine' && r.recovery_latency_ms != null)
    .map(r => r.recovery_latency_ms)

  const reactiveMttr = reactiveMttrs.length
    ? `${(reactiveMttrs.reduce((a, b) => a + b, 0) / reactiveMttrs.length).toFixed(1)} ms`
    : '—'
  const proactiveMttr = proactiveMttrs.length
    ? `${(proactiveMttrs.reduce((a, b) => a + b, 0) / proactiveMttrs.length).toFixed(1)} ms`
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
    { label: 'Avg RTT Latency',   value: avgLatency,    color: 'text-sky-400',     id: 'metric-latency'        },
    { label: 'Packet Delivery',   value: pdr,           color: 'text-emerald-400', id: 'metric-pdr'            },
    { label: 'TRAP/ML Agreement', value: agreementRate, color: 'text-indigo-400',  id: 'metric-agree'          },
    { label: 'Reactive MTTR',     value: reactiveMttr,  color: 'text-emerald-400', id: 'metric-mttr-reactive' },
    { label: 'Proactive MTTR',    value: proactiveMttr, color: 'text-amber-400',   id: 'metric-mttr-proactive'},
    { label: 'Avg Utilization',   value: avgUtil,       color: 'text-sky-300',     id: 'metric-util'           },
    { label: 'Avg Jitter',        value: avgJitter,     color: 'text-purple-400',  id: 'metric-jitter'         },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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
