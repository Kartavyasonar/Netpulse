import { useState } from 'react'
import { incidentsApi } from '../services/api'
import { usePolling } from '../hooks/usePolling'
import StatusBadge from '../components/dashboard/StatusBadge'
import { AlertTriangle, CheckCircle } from 'lucide-react'
import { formatDistanceToNow, format } from 'date-fns'

export default function IncidentsPage() {
  const [filter, setFilter] = useState(false) // false = unresolved
  const { data: incidents, refetch } = usePolling(
    () => incidentsApi.list(filter ? undefined : false),
    15000,
    [filter]
  )

  const handleResolve = async (id) => {
    await incidentsApi.resolve(id)
    refetch()
  }

  const active = (incidents || []).filter(i => !i.is_resolved)
  const resolved = (incidents || []).filter(i => i.is_resolved)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
          <AlertTriangle size={18} className="text-[#ffaa00]" /> Incidents
        </h1>
        <div className="flex gap-1">
          {[{ v: false, l: 'Active' }, { v: true, l: 'All' }].map(({ v, l }) => (
            <button
              key={String(v)}
              onClick={() => setFilter(v)}
              className={`text-xs px-3 py-1.5 rounded font-mono transition-colors ${
                filter === v
                  ? 'bg-[#1e2d4a] text-gray-200'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Active incidents */}
      {active.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-xs text-[#ff4444] font-mono">
            ● {active.length} ACTIVE INCIDENT{active.length !== 1 ? 'S' : ''}
          </h2>
          {active.map(inc => (
            <IncidentCard key={inc.id} incident={inc} onResolve={handleResolve} />
          ))}
        </div>
      )}

      {/* Resolved incidents */}
      {filter && resolved.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-xs text-gray-500 font-mono">RESOLVED</h2>
          {resolved.map(inc => (
            <IncidentCard key={inc.id} incident={inc} />
          ))}
        </div>
      )}

      {!incidents?.length && (
        <div className="noc-panel text-center py-12">
          <CheckCircle size={32} className="text-[#00ff88] mx-auto mb-3" />
          <p className="text-gray-400 text-sm">No incidents</p>
          <p className="text-gray-600 text-xs mt-1">All systems nominal</p>
        </div>
      )}
    </div>
  )
}

function IncidentCard({ incident, onResolve }) {
  const isCritical = incident.severity === 'critical'
  const borderColor = incident.is_resolved
    ? 'border-[#1e2d4a]'
    : isCritical ? 'border-[#ff4444]/40' : 'border-[#ffaa00]/40'

  return (
    <div className={`noc-panel border ${borderColor}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <StatusBadge status={incident.severity} />
            {incident.is_resolved && (
              <span className="text-[10px] text-gray-500 font-mono border border-gray-600 px-1.5 rounded">RESOLVED</span>
            )}
            <span className="text-[10px] text-gray-500">#{incident.id}</span>
          </div>
          <p className="text-sm text-gray-200 font-mono">{incident.title}</p>
          {incident.description && (
            <p className="text-xs text-gray-500 mt-1">{incident.description}</p>
          )}
          <div className="flex gap-4 mt-2 text-[10px] text-gray-600 font-mono">
            <span>Created {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}</span>
            {incident.resolved_at && (
              <span>Resolved {formatDistanceToNow(new Date(incident.resolved_at), { addSuffix: true })}</span>
            )}
            {incident.trigger_rtt_ms && <span>RTT: {incident.trigger_rtt_ms.toFixed(1)}ms</span>}
            {incident.sigma_deviation && <span>σ: {incident.sigma_deviation.toFixed(1)}</span>}
          </div>
        </div>
        {!incident.is_resolved && onResolve && (
          <button
            onClick={() => onResolve(incident.id)}
            className="text-xs text-[#00ff88] hover:bg-[#00ff88]/10 border border-[#00ff88]/30 px-3 py-1.5 rounded font-mono transition-colors shrink-0"
          >
            Resolve
          </button>
        )}
      </div>
    </div>
  )
}
