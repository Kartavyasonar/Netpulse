import { nodesApi } from '../services/api'
import { usePolling } from '../hooks/usePolling'
import { Radio, Wifi, WifiOff, AlertTriangle } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

function NodeCard({ node }) {
  const isDown = !node.is_active || node.missed_heartbeats >= 3
  const isWarning = node.missed_heartbeats > 0 && node.missed_heartbeats < 3

  const borderColor = isDown
    ? 'border-[#ff4444]/50'
    : isWarning
    ? 'border-[#ffaa00]/50'
    : 'border-[#00ff88]/20'

  const statusColor = isDown ? 'text-[#ff4444]' : isWarning ? 'text-[#ffaa00]' : 'text-[#00ff88]'
  const StatusIcon = isDown ? WifiOff : Wifi

  return (
    <div className={`noc-panel border ${borderColor}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <StatusIcon size={16} className={statusColor} />
          <div>
            <p className="text-sm text-gray-200 font-mono font-bold">
              {node.label || node.node_id}
            </p>
            <p className="text-[10px] text-gray-500">{node.node_id}</p>
          </div>
        </div>
        <span className={`text-[10px] font-mono border px-2 py-0.5 rounded ${
          node.role === 'primary'
            ? 'text-[#3b82f6] border-[#3b82f6]/30'
            : 'text-gray-400 border-gray-600'
        }`}>
          {node.role.toUpperCase()}
        </span>
      </div>

      <div className="space-y-1 text-xs font-mono">
        <div className="flex justify-between">
          <span className="text-gray-500">Region</span>
          <span className="text-gray-300">{node.region || '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Last heartbeat</span>
          <span className={node.last_heartbeat ? 'text-gray-300' : 'text-[#ff4444]'}>
            {node.last_heartbeat
              ? formatDistanceToNow(new Date(node.last_heartbeat), { addSuffix: true })
              : 'never'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Missed heartbeats</span>
          <span className={node.missed_heartbeats > 0 ? 'text-[#ffaa00]' : 'text-[#00ff88]'}>
            {node.missed_heartbeats} / {3} threshold
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Status</span>
          <span className={statusColor}>
            {isDown ? '● DOWN' : isWarning ? '● DEGRADED' : '● ACTIVE'}
          </span>
        </div>
      </div>

      {isDown && (
        <div className="mt-3 bg-[#ff4444]/10 border border-[#ff4444]/30 rounded px-2 py-1.5 text-[10px] text-[#ff4444] font-mono flex items-center gap-1.5">
          <AlertTriangle size={10} />
          Dead-man's switch triggered — alert fired
        </div>
      )}
    </div>
  )
}

export default function NodesPage() {
  const { data: nodes, loading } = usePolling(() => nodesApi.list(), 15000)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
          <Radio size={18} className="text-[#3b82f6]" /> Probe Nodes
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          Distributed vantage points — correlation detects site-local vs global outages
        </p>
      </div>

      {/* Correlation explanation */}
      <div className="noc-panel border border-[#3b82f6]/20 text-xs font-mono space-y-1">
        <p className="text-[#3b82f6] mb-2">CORRELATION LOGIC</p>
        <p className="text-gray-400">
          <span className="text-[#ffaa00]">Node A DOWN, Node B UP</span>
          {' → '}Site-local failure at Node A (not a real outage)
        </p>
        <p className="text-gray-400">
          <span className="text-[#ff4444]">Node A DOWN, Node B DOWN</span>
          {' → '}Genuine global outage — alert fires
        </p>
        <p className="text-gray-400">
          <span className="text-[#00ff88]">Both nodes UP</span>
          {' → '}All systems nominal
        </p>
      </div>

      {loading && !nodes && (
        <p className="text-gray-600 text-sm">Loading nodes...</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {(nodes || []).map(node => (
          <NodeCard key={node.node_id} node={node} />
        ))}
        {nodes?.length === 0 && (
          <div className="col-span-3 noc-panel text-center py-12 text-gray-600 text-sm">
            <Radio size={32} className="mx-auto mb-3 opacity-30" />
            <p>No probe nodes registered yet.</p>
            <p className="text-xs mt-1">
              Set up a second Oracle VPS with <code className="text-gray-400">NODE_ROLE=probe</code>
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
