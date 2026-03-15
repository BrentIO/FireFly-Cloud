import { apiFetch } from './client.js'

export function listFirmware() {
  return apiFetch('/firmware')
}

export function getFirmware(zipName) {
  return apiFetch(`/firmware/${encodeURIComponent(zipName)}`)
}

export function patchFirmwareStatus(zipName, status) {
  return apiFetch(`/firmware/${encodeURIComponent(zipName)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ release_status: status }),
  })
}

export function deleteFirmware(zipName) {
  return apiFetch(`/firmware/${encodeURIComponent(zipName)}`, {
    method: 'DELETE',
  })
}

export function getFirmwareDownloadUrl(zipName) {
  return apiFetch(`/firmware/${encodeURIComponent(zipName)}/download`)
}
