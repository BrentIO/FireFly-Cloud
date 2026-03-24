import { apiFetch } from './client.js'

export function getAppConfig() {
  return apiFetch('/appconfig')
}

export function patchAppConfig(functionName, config) {
  return apiFetch(`/appconfig/${functionName}`, {
    method: 'PATCH',
    body: JSON.stringify(config),
  })
}

export function deployAppConfig(functionName) {
  return apiFetch(`/appconfig/${functionName}/deploy`, { method: 'POST' })
}
