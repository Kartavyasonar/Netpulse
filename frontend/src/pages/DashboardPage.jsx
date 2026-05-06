import { useState } from 'react'
import { metricsApi } from '../services/api'
import { usePolling } from '../hooks/usePolling'
import StatCard from '../components/dashboard/StatCard'
import StatusBadge from '../components/dashboard/StatusBadge'
import LatencyChart from '../components/charts/LatencyChart'
import { Activity, Server, AlertTriangle, Wifi, Clock, RefreshCw } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

function HostRow({ host, onSelect, selected }) {
  return (
    <div
      onClick={() => onSelect(host)}
      className={`flex items-center gap-3 p-3 rounded cursor-pointer transition-colors ${
        selected?.host_id === host.host_id
          ? 'bg-[#1e2d4a]'
          : 'hover:bg-[#1a2035]'
      }`}
    >
      <StatusBadge status={host.status} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-200 font-mono truncate">
          {host.host_label || host.host_address}
        </p>
        <p className="text-[10px] text-gray-500">{host.host_address}</p>
      </div>
      <div className="text-right text-xs font-mono">
        <p className={host.latest_rtt_ms ? 'text-[#00ff88]' : 'text-gray-600'}>
          {host.latest_rtt_ms ? `${host.latest_rtt_ms.toFixed(1)}ms` : '—'}
        </p>
        <p className="text-gray-500 text-[10px]">
          {host.uptime_pct_24h != null ? `${host.uptime_pct_24h}% up` : '—'}
        </p>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [selectedHost, setSelectedHost] = useState(null)
  const [tsHours, setTsHours] = useState(1)

  const { data: summary, loading: sumLoading, refetch: refetchSummary } =
    usePolling(() => metricsApi.dashboard(), 30000)

  const { data: hosts, refetch: refetchHosts } =
    usePolling(() => metricsApi.summary(), 30000)

  const { data: timeseries } = usePolling(
    () => selectedHost ? metricsApi.timeseries(selectedHost.host_id, tsHours) : Promise.resolve([]),
    30000,
    [selectedHost?.host_id, tsHours]
  )

  const refetchAll = () => { refetchSummary(); refetchHosts() }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100">Network Operations Centre</h1>
          <p className="text-xs text-gray-500 mt-0.5">Live network health monitoring</p>
        </div>
        <button onClick={refetchAll} className="flex items-center gap-2 text-xs text-gray-400 hover:text-[#00ff88] transition-colors">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Hosts UP" value={summary.hosts_up} color="green" icon={Wifi} sub={`of ${summary.total_hosts} monitored`} />
          <StatCard label="Hosts DOWN" value={summary.hosts_down} color="red" icon={Server} sub={summary.hosts_degraded > 0 ? `${summary.hosts_degraded} degraded` : 'all others healthy'} />
          <StatCard label="Active Incidents" value={summary.active_incidents} color={summary.critical_incidents > 0 ? 'red' : 'yellow'} icon={AlertTriangle} sub={`${summary.critical_incidents} critical`} />
          <StatCard label="Avg RTT (1h)" value={summary.avg_rtt_ms != null ? `${summary.avg_rtt_ms}ms` : '—'} color="blue" icon={Activity} sub={`${summary.probes_last_hour} probes`} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Host list */}
        <div className="noc-panel">
          <h2 className="text-xs text-gray-400 font-mono mb-3 flex items-center gap-2">
            <Server size={12} /> HOST STATUS
            <span className="ml-auto text-gray-600">{hosts?.length || 0} hosts</span>
          </h2>
          {sumLoading && !hosts ? (
            <p className="text-gray-600 text-xs">Loading...</p>
          ) : (
            <div className="space-y-0.5 max-h-96 overflow-y-auto">
              {(hosts || []).map(h => (
                <HostRow key={h.host_id} host={h} onSelect={setSelectedHost} selected={selectedHost} />
              ))}
              {!hosts?.length && (
                <p className="text-gray-600 text-xs py-4 text-center">
                  No hosts. Add hosts or run /api/hosts/seed
                </p>
              )}
            </div>
          )}
        </div>

        {/* Latency chart */}
        <div className="noc-panel lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs text-gray-400 font-mono flex items-center gap-2">
              <Activity size={12} />
              {selectedHost
                ? `RTT — ${selectedHost.host_label || selectedHost.host_address}`
                : 'RTT TIME-SERIES — select a host'}
            </h2>
            {selectedHost && (
              <div className="flex gap-1">
                {[1, 6, 24].map(h => (
                  <button
                    key={h}
                    onClick={() => setTsHours(h)}
                    className={`text-[10px] px-2 py-0.5 rounded font-mono transition-colors ${
                      tsHours === h
                        ? 'bg-[#00ff88]/20 text-[#00ff88]'
                        : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {h}h
                  </button>
                ))}
              </div>
            )}
          </div>
          {selectedHost && timeseries ? (
            <LatencyChart data={timeseries} height={220} />
          ) : (
            <div className="flex items-center justify-center h-56 text-gray-600 text-xs">
              {selectedHost ? 'Loading chart...' : 'Click a host to view latency chart'}
            </div>
          )}
        </div>
      </div>

      {/* Auto-refresh notice */}
      <p className="text-[10px] text-gray-600 text-right font-mono">
        <Clock size={9} className="inline mr-1" />
        Auto-refreshes every 30s
      </p>
    </div>
  )
}
