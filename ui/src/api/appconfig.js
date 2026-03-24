import { apiFetch } from './client.js'

export function getAppConfig() {
  return apiFetch('/appconfig')
}

export function patchAppConfig(logging) {
  return apiFetch('/appconfig', {
    method: 'PATCH',
    body: JSON.stringify({ logging }),
  })
}
