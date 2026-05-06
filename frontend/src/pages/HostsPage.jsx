import { useState } from 'react'
import { hostsApi } from '../services/api'
import { usePolling } from '../hooks/usePolling'
import StatusBadge from '../components/dashboard/StatusBadge'
import { Plus, Trash2, Server, Zap } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

export default function HostsPage() {
  const { data: hosts, refetch } = usePolling(() => hostsApi.list(), 30000)
  const [newAddr, setNewAddr] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  const handleAdd = async () => {
    if (!newAddr.trim()) return
    setAdding(true)
    setError('')
    try {
      await hostsApi.create({ address: newAddr.trim(), label: newLabel.trim() || undefined })
      setNewAddr('')
      setNewLabel('')
      refetch()
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to add host')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this host and all its metrics?')) return
    await hostsApi.delete(id)
    refetch()
  }

  const handleSeed = async () => {
    await hostsApi.seed()
    refetch()
  }

  const handleToggle = async (host) => {
    await hostsApi.update(host.id, { is_active: !host.is_active })
    refetch()
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2">
          <Server size={18} className="text-[#00ff88]" /> Monitored Hosts
        </h1>
        <button
          onClick={handleSeed}
          className="flex items-center gap-2 text-xs text-[#3b82f6] hover:text-blue-300 border border-[#3b82f6]/30 hover:border-[#3b82f6] px-3 py-1.5 rounded transition-colors"
        >
          <Zap size={12} /> Seed defaults
        </button>
      </div>

      {/* Add host form */}
      <div className="noc-panel">
        <h2 className="text-xs text-gray-400 font-mono mb-3">ADD HOST</h2>
        <div className="flex gap-2 flex-wrap">
          <input
            value={newAddr}
            onChange={(e) => setNewAddr(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            placeholder="IP or hostname (e.g. 8.8.8.8)"
            className="flex-1 min-w-48 bg-[#0a0e1a] border border-[#1e2d4a] rounded px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:border-[#00ff88] transition-colors"
          />
          <input
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label (optional)"
            className="w-40 bg-[#0a0e1a] border border-[#1e2d4a] rounded px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:border-[#00ff88] transition-colors"
          />
          <button
            onClick={handleAdd}
            disabled={adding}
            className="flex items-center gap-1.5 bg-[#00ff88]/10 hover:bg-[#00ff88]/20 border border-[#00ff88]/40 text-[#00ff88] rounded px-4 py-2 text-sm font-mono transition-colors disabled:opacity-50"
          >
            <Plus size={14} /> Add
          </button>
        </div>
        {error && <p className="text-[#ff4444] text-xs mt-2 font-mono">{error}</p>}
      </div>

      {/* Hosts table */}
      <div className="noc-panel">
        <h2 className="text-xs text-gray-400 font-mono mb-3">{hosts?.length || 0} HOSTS</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-gray-500 border-b border-[#1e2d4a]">
                <th className="text-left pb-2 pr-4">Status</th>
                <th className="text-left pb-2 pr-4">Address</th>
                <th className="text-left pb-2 pr-4">Label</th>
                <th className="text-left pb-2 pr-4">Last Seen</th>
                <th className="text-left pb-2 pr-4">Active</th>
                <th className="text-left pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {(hosts || []).map(h => (
                <tr key={h.id} className="border-b border-[#1e2d4a]/50 hover:bg-[#1a2035]/30">
                  <td className="py-2 pr-4"><StatusBadge status={h.status} /></td>
                  <td className="py-2 pr-4 text-gray-200">{h.address}</td>
                  <td className="py-2 pr-4 text-gray-400">{h.label || '—'}</td>
                  <td className="py-2 pr-4 text-gray-500">
                    {h.last_seen
                      ? formatDistanceToNow(new Date(h.last_seen), { addSuffix: true })
                      : 'never'}
                  </td>
                  <td className="py-2 pr-4">
                    <button
                      onClick={() => handleToggle(h)}
                      className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                        h.is_active
                          ? 'text-[#00ff88] border-[#00ff88]/30 hover:bg-[#00ff88]/10'
                          : 'text-gray-500 border-gray-600 hover:bg-gray-700'
                      }`}
                    >
                      {h.is_active ? 'ACTIVE' : 'PAUSED'}
                    </button>
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => handleDelete(h.id)}
                      className="text-gray-600 hover:text-[#ff4444] transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
              {!hosts?.length && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-gray-600">
                    No hosts. Click "Seed defaults" to add Google DNS, GitHub, Cloudflare, etc.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
