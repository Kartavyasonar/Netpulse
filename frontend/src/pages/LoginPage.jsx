import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Radio } from 'lucide-react'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(form.username, form.password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Radio size={32} className="text-[#00ff88]" />
            <span className="text-[#00ff88] text-3xl font-bold tracking-widest">NetPulse</span>
          </div>
          <p className="text-gray-500 text-xs">Network Operations Centre</p>
        </div>

        {/* Form */}
        <div className="noc-panel">
          <h2 className="text-gray-300 text-sm mb-4 font-mono">OPERATOR LOGIN</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-gray-500 text-xs mb-1">USERNAME</label>
              <input
                type="text"
                value={form.username}
                onChange={(e) => setForm(f => ({ ...f, username: e.target.value }))}
                className="w-full bg-[#0a0e1a] border border-[#1e2d4a] rounded px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:border-[#00ff88] transition-colors"
                placeholder="admin"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-gray-500 text-xs mb-1">PASSWORD</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmit(e)}
                className="w-full bg-[#0a0e1a] border border-[#1e2d4a] rounded px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:border-[#00ff88] transition-colors"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-[#ff4444] text-xs font-mono">{error}</p>
            )}

            <button
              onClick={handleSubmit}
              disabled={loading}
              className="w-full bg-[#00ff88]/10 hover:bg-[#00ff88]/20 border border-[#00ff88]/40 text-[#00ff88] rounded py-2 text-sm font-mono transition-colors disabled:opacity-50"
            >
              {loading ? 'AUTHENTICATING...' : 'LOGIN →'}
            </button>
          </div>
        </div>

        <p className="text-center text-gray-600 text-[10px] mt-4 font-mono">
          Default: admin / netpulse_admin_2026
        </p>
      </div>
    </div>
  )
}
