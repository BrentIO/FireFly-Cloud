import { apiFetch } from './client.js'

export function listDevices() {
  return apiFetch('/devices')
}

export function createRegistrationKey() {
  return apiFetch('/registration-keys', { method: 'POST' })
}
