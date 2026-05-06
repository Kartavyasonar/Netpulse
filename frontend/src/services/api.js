import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${BASE_URL}/api`,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('netpulse_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('netpulse_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const authApi = {
  login: (username, password) =>
    api.post('/auth/login', { username, password }).then(r => r.data),
}

export const hostsApi = {
  list: () => api.get('/hosts').then(r => r.data),
  create: (body) => api.post('/hosts', body).then(r => r.data),
  update: (id, body) => api.patch(`/hosts/${id}`, body).then(r => r.data),
  delete: (id) => api.delete(`/hosts/${id}`).then(r => r.data),
  seed: () => api.post('/hosts/seed').then(r => r.data),
}

export const metricsApi = {
  dashboard: () => api.get('/metrics/dashboard').then(r => r.data),
  summary: () => api.get('/metrics/summary').then(r => r.data),
  timeseries: (hostId, hours = 1) =>
    api.get(`/metrics/${hostId}/timeseries`, { params: { hours } }).then(r => r.data),
}

export const incidentsApi = {
  list: (resolved) =>
    api.get('/incidents', { params: resolved !== undefined ? { resolved } : {} }).then(r => r.data),
  resolve: (id) => api.post(`/incidents/${id}/resolve`).then(r => r.data),
}

export const topologyApi = {
  graph: () => api.get('/topology/graph').then(r => r.data),
  arp: () => api.get('/topology/arp').then(r => r.data),
}

export const routesApi = {
  list: (hostId) =>
    api.get('/routes', { params: hostId ? { host_id: hostId } : {} }).then(r => r.data),
  trace: (hostId) => api.post(`/routes/${hostId}/trace`).then(r => r.data),
}

// Change 1 + 2: distributed node endpoints
// Node secret passed as header for node-to-node endpoints
const nodeSecret = import.meta.env.VITE_NODE_SECRET || ''

export const nodesApi = {
  list: () =>
    api.get('/nodes', { headers: { 'X-Node-Secret': nodeSecret } }).then(r => r.data),
}

export default api
