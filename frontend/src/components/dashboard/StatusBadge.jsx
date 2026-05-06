export default function StatusBadge({ status, size = 'sm' }) {
  const colors = {
    up: 'text-[#00ff88] bg-[#00ff88]/10 border-[#00ff88]/30',
    down: 'text-[#ff4444] bg-[#ff4444]/10 border-[#ff4444]/30',
    degraded: 'text-[#ffaa00] bg-[#ffaa00]/10 border-[#ffaa00]/30',
    unknown: 'text-gray-500 bg-gray-500/10 border-gray-500/30',
    warning: 'text-[#ffaa00] bg-[#ffaa00]/10 border-[#ffaa00]/30',
    critical: 'text-[#ff4444] bg-[#ff4444]/10 border-[#ff4444]/30',
  }
  const dots = {
    up: 'bg-[#00ff88] pulse-green',
    down: 'bg-[#ff4444] pulse-red',
    degraded: 'bg-[#ffaa00]',
    unknown: 'bg-gray-500',
    warning: 'bg-[#ffaa00]',
    critical: 'bg-[#ff4444] pulse-red',
  }

  const s = (status || 'unknown').toLowerCase()
  const px = size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-3 py-1 text-xs'

  return (
    <span className={`inline-flex items-center gap-1.5 border rounded-full font-mono ${px} ${colors[s] || colors.unknown}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[s] || dots.unknown}`} />
      {s.toUpperCase()}
    </span>
  )
}
