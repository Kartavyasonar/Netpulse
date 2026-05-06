import { useState } from 'react'
import { topologyApi } from '../services/api'
import { usePolling } from '../hooks/usePolling'
import TopologyGraph from '../components/topology/TopologyGraph'
import { Map, RefreshCw } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

export default function TopologyPage() {
  const [tab, setTab] = useState('graph')

  const { data: graph, refetch: refetchGraph } = usePolling(() => topologyApi.graph(), 30000)
  const { data: arp, refetch: refetchArp } = usePolling(() => topologyApi.arp(), 30000)

  const refetch = () => { refetchGraph(); refetchArp() }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
          <Map size={18} className="text-[#3b82f6]" /> Network Topology
        </h1>
        <button onClick={refetch} className="flex items-center gap-2 text-xs text-gray-400 hover:text-[#00ff88] transition-colors">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Stats */}
      {graph && (
        <div className="flex gap-4 text-xs font-mono text-gray-500">
          <span className="text-[#00ff88]">{graph.nodes.length} nodes</span>
          <span>{graph.edges.length} links</span>
          <span>{graph.nodes.filter(n => n.status === 'up').length} up</span>
          <span className="text-[#ff4444]">{graph.nodes.filter(n => n.status === 'down').length} down</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1">
        {['graph', 'arp'].map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 rounded font-mono uppercase transition-colors ${
              tab === t ? 'bg-[#1e2d4a] text-gray-200' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {t === 'graph' ? 'Topology Graph' : 'ARP Table'}
          </button>
        ))}
      </div>

      {tab === 'graph' && (
        <div className="noc-panel p-0 overflow-hidden">
          <TopologyGraph graph={graph} height={520} />
        </div>
      )}

      {tab === 'arp' && (
        <div className="noc-panel">
          <h2 className="text-xs text-gray-400 font-mono mb-3">ARP TABLE — MAC to IP mappings</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-gray-500 border-b border-[#1e2d4a]">
                  <th className="text-left pb-2 pr-4">IP Address</th>
                  <th className="text-left pb-2 pr-4">MAC Address</th>
                  <th className="text-left pb-2 pr-4">Interface</th>
                  <th className="text-left pb-2 pr-4">State</th>
                  <th className="text-left pb-2 pr-4">Last Seen</th>
                  <th className="text-left pb-2">Active</th>
                </tr>
              </thead>
              <tbody>
                {(arp || []).map(entry => (
                  <tr key={entry.id} className="border-b border-[#1e2d4a]/40 hover:bg-[#1a2035]/30">
                    <td className="py-2 pr-4 text-[#00ff88]">{entry.ip_address}</td>
                    <td className="py-2 pr-4 text-gray-300">{entry.mac_address}</td>
                    <td className="py-2 pr-4 text-gray-500">{entry.interface || '—'}</td>
                    <td className="py-2 pr-4 text-gray-400">{entry.state || '—'}</td>
                    <td className="py-2 pr-4 text-gray-500">
                      {formatDistanceToNow(new Date(entry.last_seen), { addSuffix: true })}
                    </td>
                    <td className="py-2">
                      <span className={entry.is_active ? 'text-[#00ff88]' : 'text-gray-600'}>
                        {entry.is_active ? '●' : '○'}
                      </span>
                    </td>
                  </tr>
                ))}
                {!arp?.length && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-gray-600">
                      No ARP entries yet. ARP table populates after first probe cycle.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
