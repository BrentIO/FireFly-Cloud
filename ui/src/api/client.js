import { useAuth } from '../composables/useAuth.js'
import router from '../router/index.js'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.p5software.com'

export async function apiFetch(path, options = {}) {
  const auth  = useAuth()
  const token = auth.getAccessToken()

  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers })

  if (res.status === 401) {
    // Token rejected — clear session and redirect to login
    await auth.logout()
    return
  }

  let body
  try { body = await res.json() } catch { body = null }

  if (!res.ok) {
    const err    = new Error(body?.message || `HTTP ${res.status}`)
    err.status   = res.status
    err.body     = body
    throw err
  }

  return body
}
