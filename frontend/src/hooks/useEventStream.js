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
  }, [])

  useEffect(() => {
    const cleanup = connectEventStream(handleMessage, setWsStatus)
    return cleanup
  }, [handleMessage])

  return { alerts, reroutes, telemetry, wsStatus, clearAll }
}
