import { apiFetch } from './client.js'

export function listRegistrationKeys() {
  return apiFetch('/registration-keys')
}

export function createRegistrationKey() {
  return apiFetch('/registration-keys', { method: 'POST' })
}
