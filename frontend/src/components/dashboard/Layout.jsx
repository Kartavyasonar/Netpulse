import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import {
  Activity, Server, AlertTriangle, GitBranch, Map, LogOut, Radio
} from 'lucide-react'
import { useState, useEffect } from 'react'

const NAV = [
  { to: '/', label: 'Dashboard', icon: Activity, end: true },
  { to: '/hosts', label: 'Hosts', icon: Server },
  { to: '/incidents', label: 'Incidents', icon: AlertTriangle },
  { to: '/topology', label: 'Topology', icon: Map },
  { to: '/routes', label: 'Routes', icon: GitBranch },
  { to: '/nodes', label: 'Probe Nodes', icon: Radio },
]

export default function Layout() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="flex h-screen bg-[#0a0e1a] overflow-hidden">
      <aside className="w-56 bg-[#0f1629] border-r border-[#1e2d4a] flex flex-col">
        <div className="p-4 border-b border-[#1e2d4a]">
          <div className="flex items-center gap-2">
            <Radio size={20} className="text-[#00ff88]" />
            <span className="text-[#00ff88] font-bold text-lg tracking-wider">NetPulse</span>
          </div>
          <p className="text-[10px] text-gray-500 mt-1">Network Operations Centre</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                  isActive
                    ? 'bg-[#1e2d4a] text-[#00ff88]'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-[#1a2035]'
                }`
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-[#1e2d4a]">
          <p className="text-[10px] text-gray-500 mb-1">UTC</p>
          <p className="text-[#00ff88] text-xs font-mono mb-3">
            {now.toISOString().replace('T', ' ').slice(0, 19)}
          </p>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-gray-500 hover:text-red-400 text-xs transition-colors w-full"
          >
            <LogOut size={13} /> Logout
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
