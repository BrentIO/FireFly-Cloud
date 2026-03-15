const API_URL = import.meta.env.VITE_API_URL || 'https://api.p5software.com'

export async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  let body
  try { body = await res.json() } catch { body = null }
  if (!res.ok) {
    const err = new Error(body?.message || `HTTP ${res.status}`)
    err.status = res.status
    err.body = body
    throw err
  }
  return body
}
