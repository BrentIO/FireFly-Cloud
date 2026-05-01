import { apiFetch } from './client.js'

export function listDevices() {
  return apiFetch('/devices')
}
