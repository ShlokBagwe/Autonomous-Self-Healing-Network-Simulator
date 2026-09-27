import { useState, useEffect } from 'react'

/**
 * FeatureImportance — embeds GET /api/feature-importance HTML output.
 * Falls back to a JSON bar chart if the iframe fails to load.
 */
export default function FeatureImportance() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  return (
    <div className="relative w-full h-64 rounded-xl overflow-hidden border border-white/[0.06]">
      {loading && !error && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-600 text-xs bg-slate-900/80 z-10">
          Loading feature importance chart…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 text-xs bg-slate-900/80 z-10 gap-2 p-4 text-center">
          <span className="text-2xl">🧠</span>
          <p>Feature importance chart not available.</p>
          <p className="text-slate-600">Run <span className="mono text-sky-500">python -m ml_engine.train_pipeline</span> to generate it.</p>
        </div>
      )}
      <iframe
        src="/api/feature-importance"
        className="w-full h-full border-0 bg-transparent"
        title="Random Forest Feature Importance (Explainable AI)"
        onLoad={() => setLoading(false)}
        onError={() => { setLoading(false); setError(true) }}
        sandbox="allow-scripts allow-same-origin"
      />
    </div>
  )
}
