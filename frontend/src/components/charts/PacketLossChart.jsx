import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'
import { format } from 'date-fns'

export default function PacketLossChart({ data = [], height = 120 }) {
  const formatted = data.map((d) => ({
    time: format(new Date(d.timestamp), 'HH:mm'),
    loss: d.packet_loss_pct,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={formatted} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ff4444" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#ff4444" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4a" />
        <XAxis dataKey="time" tick={{ fill: '#4a5568', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#4a5568', fontSize: 10 }} unit="%" domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: '#0f1629', border: '1px solid #1e2d4a', borderRadius: 4 }}
          labelStyle={{ color: '#4a5568', fontSize: 10 }}
          itemStyle={{ color: '#ff4444', fontSize: 10 }}
          formatter={(v) => [`${v.toFixed(1)}%`, 'Packet Loss']}
        />
        <Area
          type="monotone"
          dataKey="loss"
          stroke="#ff4444"
          strokeWidth={1.5}
          fill="url(#lossGrad)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
