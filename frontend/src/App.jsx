import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import HostsPage from './pages/HostsPage'
import IncidentsPage from './pages/IncidentsPage'
import TopologyPage from './pages/TopologyPage'
import RoutesPage from './pages/RoutesPage'
import NodesPage from './pages/NodesPage'
import Layout from './components/dashboard/Layout'

function PrivateRoute({ children }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }>
            <Route index element={<DashboardPage />} />
            <Route path="hosts" element={<HostsPage />} />
            <Route path="incidents" element={<IncidentsPage />} />
            <Route path="topology" element={<TopologyPage />} />
            <Route path="routes" element={<RoutesPage />} />
            <Route path="nodes" element={<NodesPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
