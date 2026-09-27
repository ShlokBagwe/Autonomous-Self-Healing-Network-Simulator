// REST and WebSocket client — all calls go through the Vite dev proxy
// which forwards /api/* and /ws/* to http://localhost:8000

const BASE = ''  // proxy handles routing in dev; in prod, same origin via FastAPI

// ─── REST ────────────────────────────────────────────────────────────────────

export async function fetchTopology() {
  const res = await fetch(`${BASE}/api/topology`)
  if (!res.ok) throw new Error(`topology fetch failed: ${res.status}`)
  return res.json()
}

export async function postFault(kind, target) {
  const res = await fetch(`${BASE}/api/fault`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind, target }),
  })
  if (!res.ok) throw new Error(`fault inject failed: ${res.status}`)
  return res.json()
}

export async function postReset() {
  const res = await fetch(`${BASE}/api/reset`, { method: 'POST' })
  if (!res.ok) throw new Error(`reset failed: ${res.status}`)
  return res.json()
}

export async function fetchReconciliation() {
  const res = await fetch(`${BASE}/api/reconciliation`)
  if (!res.ok) throw new Error(`reconciliation fetch failed: ${res.status}`)
  return res.json()
}

// ─── WebSocket ────────────────────────────────────────────────────────────────

const WS_URL =
  (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
  window.location.host +
  '/ws/events'

/**
 * Open a WebSocket to /ws/events.
 * onMessage(parsedPayload) is called for every JSON message received.
 * Returns a cleanup function to close the socket.
 */
export function connectEventStream(onMessage, onStatusChange) {
  let ws = null
  let reconnectTimer = null
  let stopped = false

  function connect() {
    if (stopped) return
    ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      onStatusChange?.('connected')
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        onMessage(msg)
      } catch (e) {
        console.error('[ws] parse error', e)
      }
    }

    ws.onclose = () => {
      onStatusChange?.('reconnecting')
      if (!stopped) {
        reconnectTimer = setTimeout(connect, 2000)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }

  connect()

  return () => {
    stopped = true
    clearTimeout(reconnectTimer)
    ws?.close()
  }
}
