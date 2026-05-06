import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { format } from 'date-fns'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#0f1629] border border-[#1e2d4a] rounded px-3 py-2 text-xs font-mono">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value != null ? `${p.value.toFixed(2)}ms` : '—'}
        </p>
      ))}
    </div>
  )
}

export default function LatencyChart({ data = [], height = 180 }) {
  const formatted = data.map((d) => ({
    ...d,
    time: format(new Date(d.timestamp), 'HH:mm'),
    rtt: d.is_reachable ? d.rtt_ms : null,
  }))

  const rtts = formatted.filter(d => d.rtt != null).map(d => d.rtt)
  const avg = rtts.length ? rtts.reduce((a, b) => a + b, 0) / rtts.length : null

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={formatted} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4a" />
        <XAxis
          dataKey="time"
          tick={{ fill: '#4a5568', fontSize: 10, fontFamily: 'monospace' }}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: '#4a5568', fontSize: 10, fontFamily: 'monospace' }}
          unit="ms"
        />
        <Tooltip content={<CustomTooltip />} />
        {avg && (
          <ReferenceLine
            y={avg}
            stroke="#3b82f6"
            strokeDasharray="4 2"
            label={{ value: `avg ${avg.toFixed(1)}ms`, fill: '#3b82f6', fontSize: 9 }}
          />
        )}
        <Line
          type="monotone"
          dataKey="rtt"
          name="RTT"
          stroke="#00ff88"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
          activeDot={{ r: 3, fill: '#00ff88' }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
