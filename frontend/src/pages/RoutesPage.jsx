import { useState } from 'react'
import { routesApi, hostsApi } from '../services/api'
import { usePolling } from '../hooks/usePolling'
import { GitBranch, Play } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

function HopRow({ hop, index }) {
  const hasReply = hop.ip != null
  return (
    <div className={`flex items-center gap-3 text-xs font-mono py-1.5 border-b border-[#1e2d4a]/30 ${
      !hasReply ? 'opacity-40' : ''
    }`}>
      <span className="w-6 text-gray-600 text-right">{hop.ttl}</span>
      <span className="flex-1 text-gray-300">{hop.ip || '* * *'}</span>
      <span className={hop.rtt_ms ? (hop.rtt_ms > 100 ? 'text-[#ffaa00]' : 'text-[#00ff88]') : 'text-gray-600'}>
        {hop.rtt_ms ? `${hop.rtt_ms.toFixed(2)}ms` : '—'}
      </span>
    </div>
  )
}

export default function RoutesPage() {
  const [selectedHost, setSelectedHost] = useState(null)
  const [tracing, setTracing] = useState(false)

  const { data: hosts } = usePolling(() => hostsApi.list(), 60000)
  const { data: traces, refetch } = usePolling(
    () => selectedHost ? routesApi.list(selectedHost.id) : routesApi.list(),
    30000,
    [selectedHost?.id]
  )

  const handleTrace = async () => {
    if (!selectedHost) return
    setTracing(true)
    try {
      await routesApi.trace(selectedHost.id)
      refetch()
    } finally {
      setTracing(false)
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
          <GitBranch size={18} className="text-[#ffaa00]" /> Route Traces
        </h1>
      </div>

      {/* Controls */}
      <div className="noc-panel flex items-center gap-3 flex-wrap">
        <select
          value={selectedHost?.id || ''}
          onChange={(e) => {
            const h = hosts?.find(x => x.id === +e.target.value)
            setSelectedHost(h || null)
          }}
          className="bg-[#0a0e1a] border border-[#1e2d4a] text-sm text-gray-300 rounded px-3 py-2 font-mono focus:outline-none focus:border-[#00ff88]"
        >
          <option value="">All hosts</option>
          {(hosts || []).map(h => (
            <option key={h.id} value={h.id}>{h.label || h.address}</option>
          ))}
        </select>
        {selectedHost && (
          <button
            onClick={handleTrace}
            disabled={tracing}
            className="flex items-center gap-2 text-xs bg-[#ffaa00]/10 hover:bg-[#ffaa00]/20 border border-[#ffaa00]/40 text-[#ffaa00] rounded px-4 py-2 font-mono transition-colors disabled:opacity-50"
          >
            <Play size={12} /> {tracing ? 'Tracing...' : 'Run trace now'}
          </button>
        )}
      </div>

      {/* Trace list */}
      <div className="space-y-3">
        {(traces || []).map(trace => (
          <div key={trace.id} className="noc-panel">
            <div className="flex items-center justify-between mb-3">
              <div>
                <span className="text-xs text-gray-400 font-mono">
                  Host #{trace.host_id} • {trace.hop_count} hops
                </span>
                {trace.path_changed && (
                  <span className="ml-2 text-[10px] text-[#ffaa00] border border-[#ffaa00]/30 px-1.5 py-0.5 rounded font-mono">
                    ROUTE CHANGED
                  </span>
                )}
              </div>
              <span className="text-[10px] text-gray-600 font-mono">
                {formatDistanceToNow(new Date(trace.timestamp), { addSuffix: true })}
              </span>
            </div>

            {trace.path_changed && trace.diff_summary && (
              <p className="text-[10px] text-[#ffaa00] bg-[#ffaa00]/5 border border-[#ffaa00]/20 rounded px-2 py-1.5 mb-2 font-mono">
                {trace.diff_summary}
              </p>
            )}

            <div className="border-t border-[#1e2d4a] pt-2">
              <div className="flex text-[10px] text-gray-600 font-mono mb-1 gap-3">
                <span className="w-6">TTL</span>
                <span className="flex-1">IP Address</span>
                <span>RTT</span>
              </div>
              {trace.hops.map((hop, i) => (
                <HopRow key={i} hop={hop} index={i} />
              ))}
            </div>
          </div>
        ))}
        {!traces?.length && (
          <div className="noc-panel text-center py-12 text-gray-600 text-sm">
            No route traces yet. Select a host and click "Run trace now".
          </div>
        )}
      </div>
    </div>
  )
}
