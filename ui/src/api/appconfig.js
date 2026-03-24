import { apiFetch } from './client.js'

export function listAppConfig() {
  return apiFetch('/appconfig')
}

export function postAppConfig(name, logging) {
  return apiFetch('/appconfig', {
    method: 'POST',
    body: JSON.stringify({ name, logging }),
  })
}

export function patchAppConfig(applicationName, logging) {
  return apiFetch(`/appconfig/${encodeURIComponent(applicationName)}`, {
    method: 'PATCH',
    body: JSON.stringify({ logging }),
  })
}
