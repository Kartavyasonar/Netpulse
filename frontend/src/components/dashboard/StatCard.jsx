export default function StatCard({ label, value, sub, color = 'green', icon: Icon }) {
  const colors = {
    green: 'text-[#00ff88]',
    red: 'text-[#ff4444]',
    yellow: 'text-[#ffaa00]',
    blue: 'text-[#3b82f6]',
    gray: 'text-gray-400',
  }

  return (
    <div className="noc-panel flex flex-col gap-1">
      <div className="flex items-center justify-between text-gray-500 text-xs mb-1">
        <span>{label}</span>
        {Icon && <Icon size={14} />}
      </div>
      <div className={`text-3xl font-bold ${colors[color]}`}>{value ?? '—'}</div>
      {sub && <div className="text-[10px] text-gray-500">{sub}</div>}
    </div>
  )
}
