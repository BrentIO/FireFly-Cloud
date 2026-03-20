import { apiFetch } from './client.js'

export function listUsers() {
  return apiFetch('/users')
}

export function inviteUser({ email, environments }) {
  return apiFetch('/users', {
    method: 'POST',
    body: JSON.stringify({ email, environments }),
  })
}

export function deleteUser(email) {
  return apiFetch(`/users/${encodeURIComponent(email)}`, { method: 'DELETE' })
}

export function patchUser(email, patch) {
  return apiFetch(`/users/${encodeURIComponent(email)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}
