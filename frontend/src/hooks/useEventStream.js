import { useEffect, useRef, useState, useCallback } from 'react'
import { connectEventStream } from '../api/client'

/**
 * useEventStream — subscribes to /ws/events and exposes accumulated state.
 *
 * Returns:
 *   alerts      — Array<Alert payload> (newest first, capped at 100)
 *   reroutes    — Array<RerouteEvent payload> (newest first, capped at 50)
 *   telemetry   — Map<link, latest TelemetryReading>
 *   wsStatus    — 'connected' | 'reconnecting'
 *   clearAll()  — reset all accumulated state
 */
export function useEventStream() {
  const [alerts, setAlerts] = useState([])
  const [reroutes, setReroutes] = useState([])
  const [telemetry, setTelemetry] = useState(new Map())
  const [metricsSummary, setMetricsSummary] = useState(null)
  const [wsStatus, setWsStatus] = useState('reconnecting')

  const handleMessage = useCallback((msg) => {
    const { type, payload } = msg
    if (!payload) return

    if (type === 'telemetry.reading') {
      setTelemetry((prev) => {
        const next = new Map(prev)
        next.set(payload.link, payload)
        return next
      })
    } else if (type === 'metrics.summary') {
      setMetricsSummary(payload)
      // Prune inactive/down links from telemetry map so stale readings are never carried over
      if (Array.isArray(payload.active_links)) {
        const activeSet = new Set(payload.active_links)
        setTelemetry((prev) => {
          let changed = false
          const next = new Map()
          for (const [k, v] of prev.entries()) {
            if (activeSet.has(k)) {
              next.set(k, v)
            } else {
              changed = true
            }
          }
          return changed ? next : prev
        })
      }
    } else if (type === 'alert.raised') {
      setAlerts((prev) => [{ ...payload, _id: Date.now() + Math.random() }, ...prev].slice(0, 100))
    } else if (type === 'reroute.completed') {
      setReroutes((prev) => [{ ...payload, _id: Date.now() + Math.random() }, ...prev].slice(0, 50))
    }
  }, [])

  const clearAll = useCallback(() => {
    setAlerts([])
    setReroutes([])
    setTelemetry(new Map())
    setMetricsSummary(null)
  }, [])

  useEffect(() => {
    const cleanup = connectEventStream(handleMessage, setWsStatus)
    return cleanup
  }, [handleMessage])

  return { alerts, reroutes, telemetry, metricsSummary, wsStatus, clearAll }
}
