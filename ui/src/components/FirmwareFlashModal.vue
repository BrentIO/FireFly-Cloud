<script setup>
import { ref, computed, onUnmounted } from 'vue'
import {
  XMarkIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/vue/24/outline'
import { ESPLoader, Transport } from 'esptool-js'
import JSZip from 'jszip'
import SparkMD5 from 'spark-md5'
import { getFirmwareDownloadUrl } from '../api/firmware.js'
import { useToast } from '../composables/useToast.js'

const props = defineProps({
  open: { type: Boolean, required: true },
  item: { type: Object, required: true },
  zipName: { type: String, required: true },
})

const emit = defineEmits(['close'])

const { error: toastError } = useToast()

// phase: idle | downloading | connecting | flashing | done | error
const phase = ref('idle')
const statusMessage = ref('')
const errorMessage = ref('')
const chipName = ref('')
const macAddress = ref('')
const eraseMessage = ref('')
const fileProgress = ref([]) // [{ name, address, written, total }]
const eraseAll = ref(false)

let transport = null

// ---------------------------------------------------------------------------
// Addresses fixed by ESP32 architecture — the same on every board:
//   bootloader  → 0x01000
//   partitions  → 0x08000
//   application → 0x10000  (standard app0 offset)
//
// Addresses for data partitions (config, www, etc.) are resolved from the
// partition_offsets map stored in the DynamoDB record at ingestion time.
// Non-.bin files (*.elf, *.map, manifest.json, etc.) are always skipped.
// ---------------------------------------------------------------------------

/**
 * Resolve the flash address for a file.
 * Returns null for files that should be skipped.
 * partition_offsets values may be strings (DynamoDB Decimal → JSON default=str).
 */
function resolveFlashAddress(filename) {
  const offsets = props.item.partition_offsets || {}
  if (filename.endsWith('.bootloader.bin')) return 0x01000
  if (filename.endsWith('.partitions.bin')) return 0x08000
  if (filename === 'config.bin') {
    const v = offsets['config']
    return v != null ? Number(v) : null
  }
  if (filename === 'www.bin') {
    const v = offsets['www']
    return v != null ? Number(v) : null
  }
  if (filename.endsWith('.bin')) return 0x10000
  return null
}

/**
 * Display label for the idle-state file table.
 * Uses stored partition_offsets for data partitions when available.
 */
function displayAddress(filename) {
  if (filename.endsWith('.bootloader.bin')) return '0x01000'
  if (filename.endsWith('.partitions.bin')) return '0x08000'
  if (filename === 'config.bin') {
    const v = (props.item.partition_offsets || {})['config']
    return v != null ? formatAddress(Number(v)) : 'from partition table'
  }
  if (filename === 'www.bin') {
    const v = (props.item.partition_offsets || {})['www']
    return v != null ? formatAddress(Number(v)) : 'from partition table'
  }
  if (filename.endsWith('.bin')) return '0x10000'
  return null
}

function formatAddress(addr) {
  return '0x' + addr.toString(16).toUpperCase().padStart(5, '0')
}

// Files shown in the idle-state table
const displayFiles = computed(() => {
  const bins = (props.item.files || []).filter(f => f.name.endsWith('.bin'))
  const skipped = (props.item.files || []).filter(f => !f.name.endsWith('.bin'))
  return [
    ...bins.map(f => ({ name: f.name, label: displayAddress(f.name), skipped: false })),
    ...skipped.map(f => ({ name: f.name, label: null, skipped: true })),
  ]
})

// ---------------------------------------------------------------------------
// IndexedDB firmware cache — keyed by zipName, max MAX_CACHED entries (LRU)
// ---------------------------------------------------------------------------
const DB_NAME = 'firefly-firmware-cache'
const STORE_NAME = 'firmware'
const MAX_CACHED = 3

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = (e) => {
      const db = e.target.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'zipName' })
        store.createIndex('cachedAt', 'cachedAt', { unique: false })
      }
    }
    req.onsuccess = (e) => resolve(e.target.result)
    req.onerror = (e) => reject(e.target.error)
  })
}

async function getCachedZip(zipName) {
  try {
    const db = await openDb()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const req = tx.objectStore(STORE_NAME).get(zipName)
      req.onsuccess = (e) => resolve(e.target.result?.data ?? null)
      req.onerror = (e) => reject(e.target.error)
    })
  } catch {
    return null
  }
}

async function cacheZip(zipName, buffer) {
  try {
    const db = await openDb()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    await new Promise((resolve, reject) => {
      const countReq = store.count()
      countReq.onsuccess = () => {
        const count = countReq.result
        if (count >= MAX_CACHED) {
          // Evict oldest entries until we are under the limit
          const index = store.index('cachedAt')
          const cursorReq = index.openCursor()
          let deleted = 0
          const toDelete = count - MAX_CACHED + 1
          cursorReq.onsuccess = (e) => {
            const cursor = e.target.result
            if (cursor && deleted < toDelete) {
              cursor.delete()
              deleted++
              cursor.continue()
            } else {
              store.put({ zipName, data: buffer, cachedAt: Date.now() })
            }
          }
          cursorReq.onerror = (e) => reject(e.target.error)
        } else {
          store.put({ zipName, data: buffer, cachedAt: Date.now() })
        }
      }
      countReq.onerror = (e) => reject(e.target.error)
      tx.oncomplete = () => resolve()
      tx.onerror = (e) => reject(e.target.error)
    })
  } catch {
    // Cache write failure is non-fatal — proceed without caching
  }
}

// ---------------------------------------------------------------------------
// Flash sequence
// ---------------------------------------------------------------------------
async function startFlash() {
  const offsets = props.item.partition_offsets
  if (offsets == null || Object.keys(offsets).length === 0) {
    toastError('Cannot flash: partition offset data is missing from this firmware record.')
    return
  }

  phase.value = 'downloading'
  errorMessage.value = ''
  chipName.value = ''
  fileProgress.value = []

  try {
    // 1. Request Web Serial port first — must happen directly within the user
    //    gesture handler before any awaited network calls, otherwise the browser
    //    rejects it with "Must be handling a user gesture".
    phase.value = 'connecting'
    statusMessage.value = 'Waiting for port selection…'
    console.log('[FireFly Flash] Requesting serial port…')
    const port = await navigator.serial.requestPort()
    console.log('[FireFly Flash] Port selected:', port)

    // 2. Get ZIP from local cache or download from S3
    phase.value = 'downloading'
    let zipBuffer = await getCachedZip(props.zipName)
    if (zipBuffer) {
      console.log('[FireFly Flash] Cache hit for', props.zipName)
      statusMessage.value = 'Loading firmware from cache…'
    } else {
      console.log('[FireFly Flash] Cache miss for', props.zipName, '— downloading')
      statusMessage.value = 'Fetching download URL…'
      const { url } = await getFirmwareDownloadUrl(props.zipName)
      statusMessage.value = 'Downloading firmware ZIP…'
      const response = await fetch(url)
      if (!response.ok) throw new Error(`Download failed (HTTP ${response.status})`)
      zipBuffer = await response.arrayBuffer()
      cacheZip(props.zipName, zipBuffer) // fire-and-forget; failure is non-fatal
    }

    // 3. Load ZIP and build the ordered file array
    statusMessage.value = 'Extracting firmware files…'
    const zip = await JSZip.loadAsync(zipBuffer)

    const binFiles = (props.item.files || []).filter(f => f.name.endsWith('.bin'))
    const fileArray = []
    for (const f of binFiles) {
      const address = resolveFlashAddress(f.name)
      if (address === null) continue // address unknown; skip
      const entry = zip.file(f.name)
      if (!entry) throw new Error(`File not found in ZIP: ${f.name}`)
      const data = await entry.async('binarystring')
      fileArray.push({ data, address, name: f.name })
    }
    // Sort by address so flashing proceeds low → high
    fileArray.sort((a, b) => a.address - b.address)

    if (fileArray.length === 0) {
      toastError('Cannot flash: no flashable files found.')
      phase.value = 'idle'
      return
    }

    // Initialise progress tracking now that we have the final file list
    fileProgress.value = fileArray.map(f => ({ name: f.name, address: f.address, written: 0, total: 0 }))

    // 4. Connect via esptool-js (port already obtained in step 1)
    console.log('[FireFly Flash] Creating Transport and ESPLoader…')
    transport = new Transport(port, false)
    const terminal = {
      clean() {},
      writeLine(s) {
        console.log('[ESP]', s)
        const macMatch = s.match(/mac:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})/i)
        if (macMatch) macAddress.value = macMatch[1].toUpperCase()
        if (s.toLowerCase().includes('erasing flash')) eraseMessage.value = s
      },
      write(s) { console.log('[ESP]', s) },
    }
    const esploader = new ESPLoader({ transport, baudrate: 921600, terminal })

    statusMessage.value = 'Connecting to device…'
    console.log('[FireFly Flash] Running ESPLoader.main()…')
    const chip = await esploader.main()
    console.log('[FireFly Flash] Chip detected:', chip)
    chipName.value = chip || 'ESP32'

    // 5. Flash
    phase.value = 'flashing'
    console.log('[FireFly Flash] Starting writeFlash with', fileArray.length, 'file(s)…')
    await esploader.writeFlash({
      fileArray: fileArray.map(({ data, address }) => ({ data, address })),
      flashSize: 'keep',
      flashMode: 'keep',
      flashFreq: 'keep',
      eraseAll: eraseAll.value,
      compress: true,
      reportProgress(fileIndex, written, total) {
        if (fileProgress.value[fileIndex]) {
          fileProgress.value[fileIndex].written = written
          fileProgress.value[fileIndex].total = total
        }
      },
      calculateMD5Hash(image) {
        return SparkMD5.hashBinary(image, false)
      },
    })

    console.log('[FireFly Flash] writeFlash complete')
    phase.value = 'done'
  } catch (err) {
    console.log('[FireFly Flash] Error caught:', err)
    if (err?.name === 'NotAllowedError' || err?.message?.includes('No port selected')) {
      phase.value = 'idle'
      return
    }
    errorMessage.value = err.message || String(err)
    phase.value = 'error'
  } finally {
    if (transport) {
      try { await transport.disconnect() } catch (_) {}
      transport = null
    }
  }
}

function reset() {
  phase.value = 'idle'
  errorMessage.value = ''
  chipName.value = ''
  macAddress.value = ''
  eraseMessage.value = ''
  fileProgress.value = []
  eraseAll.value = false
}

function handleClose() {
  if (phase.value === 'flashing') return
  reset()
  emit('close')
}

onUnmounted(async () => {
  if (transport) {
    try { await transport.disconnect() } catch (_) {}
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="open" class="fixed inset-0 z-[60] overflow-y-auto" role="dialog" aria-modal="true">
        <!-- Backdrop -->
        <div class="fixed inset-0 bg-black/60" @click="handleClose" />

        <!-- Panel -->
        <div class="flex min-h-full items-center justify-center p-4">
          <Transition
            enter-active-class="transition ease-out duration-200"
            enter-from-class="opacity-0 scale-95"
            enter-to-class="opacity-100 scale-100"
            leave-active-class="transition ease-in duration-150"
            leave-from-class="opacity-100 scale-100"
            leave-to-class="opacity-0 scale-95"
          >
            <div
              v-if="open"
              class="relative w-full max-w-lg rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 overflow-hidden"
            >
              <!-- Header -->
              <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                <div>
                  <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">Flash via USB</h3>
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {{ item.product_id }} &mdash; {{ item.version }} ({{ item.commit?.slice(0, 7) }})
                  </p>
                </div>
                <button
                  @click="handleClose"
                  :disabled="phase === 'flashing'"
                  class="ml-4 flex-shrink-0 rounded-md p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  aria-label="Close"
                >
                  <XMarkIcon class="w-5 h-5" />
                </button>
              </div>

              <!-- Body -->
              <div class="px-6 py-5 space-y-4">

                <!-- ── Idle ── -->
                <template v-if="phase === 'idle'">
                  <p class="text-sm text-gray-700 dark:text-gray-300">
                    The following files will be written to your device's flash memory.
                    Connect a USB cable and click <strong>Connect &amp; Flash</strong> to begin.
                  </p>

                  <div class="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <table class="w-full text-sm">
                      <thead class="bg-gray-50 dark:bg-gray-800">
                        <tr>
                          <th class="text-left px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">File</th>
                          <th class="text-right px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Flash Address</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
                        <tr
                          v-for="f in displayFiles"
                          :key="f.name"
                          class="bg-white dark:bg-gray-900"
                        >
                          <td class="px-4 py-2 font-mono text-xs"
                              :class="f.skipped ? 'text-gray-400 dark:text-gray-600' : 'text-gray-900 dark:text-gray-100'">
                            {{ f.name }}
                          </td>
                          <td class="px-4 py-2 text-xs text-right"
                              :class="f.skipped ? 'text-gray-400 dark:text-gray-600 italic' : 'font-mono text-gray-500 dark:text-gray-400'">
                            {{ f.skipped ? 'skipped' : f.label }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Erase all flash option -->
                  <label class="flex items-start gap-3 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      v-model="eraseAll"
                      class="mt-0.5 h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    />
                    <span class="text-sm text-gray-700 dark:text-gray-300">
                      Erase all flash before writing
                      <span class="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        Wipes the entire flash chip before flashing. Use when replacing firmware
                        from a different project or to clear stale partition data.
                      </span>
                    </span>
                  </label>

                  <p class="text-xs text-gray-500 dark:text-gray-400">
                    If your device does not reset automatically, hold <strong>BOOT</strong>
                    while pressing <strong>EN</strong> to enter bootloader mode before connecting.
                  </p>
                </template>

                <!-- ── Downloading / Connecting ── -->
                <template v-else-if="phase === 'downloading' || phase === 'connecting'">
                  <div class="flex flex-col items-center gap-4 py-6">
                    <svg class="animate-spin w-10 h-10 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    <p class="text-sm text-gray-700 dark:text-gray-300 text-center">{{ statusMessage }}</p>
                    <p v-if="phase === 'connecting'" class="text-xs text-gray-500 dark:text-gray-400 text-center">
                      Select your device's serial port in the browser dialog.
                    </p>
                  </div>
                </template>

                <!-- ── Flashing ── -->
                <template v-else-if="phase === 'flashing'">
                  <p class="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Flashing {{ chipName }}…
                  </p>
                  <p v-if="macAddress" class="text-xs font-mono text-gray-500 dark:text-gray-400 -mt-2">
                    MAC: {{ macAddress }}
                  </p>
                  <p v-if="eraseMessage" class="text-xs text-amber-600 dark:text-amber-400">
                    {{ eraseMessage }}
                  </p>
                  <div class="space-y-3">
                    <div v-for="f in fileProgress" :key="f.name">
                      <div class="flex items-center justify-between mb-1">
                        <span class="font-mono text-xs text-gray-700 dark:text-gray-300">
                          {{ f.name }}
                          <span class="text-gray-400 dark:text-gray-500 ml-1">({{ formatAddress(f.address) }})</span>
                        </span>
                        <span class="text-xs text-gray-500 dark:text-gray-400">
                          {{ f.total > 0 ? Math.round((f.written / f.total) * 100) : 0 }}%
                        </span>
                      </div>
                      <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                        <div
                          class="bg-blue-600 h-1.5 rounded-full transition-all duration-200"
                          :style="{ width: f.total > 0 ? `${(f.written / f.total) * 100}%` : '0%' }"
                        />
                      </div>
                    </div>
                  </div>
                  <p class="text-xs text-amber-600 dark:text-amber-400">
                    Do not disconnect the device during flashing.
                  </p>
                </template>

                <!-- ── Done ── -->
                <template v-else-if="phase === 'done'">
                  <div class="flex flex-col items-center gap-3 py-6">
                    <CheckCircleIcon class="w-12 h-12 text-green-500" />
                    <p class="text-base font-semibold text-gray-900 dark:text-gray-100">Firmware flashed successfully!</p>
                    <p class="text-sm text-gray-500 dark:text-gray-400 text-center">
                      Your device has been reset and is running the new firmware.
                    </p>
                  </div>
                </template>

                <!-- ── Error ── -->
                <template v-else-if="phase === 'error'">
                  <div class="flex flex-col items-center gap-3 py-6">
                    <ExclamationCircleIcon class="w-12 h-12 text-red-500" />
                    <p class="text-base font-semibold text-gray-900 dark:text-gray-100">Flashing failed</p>
                    <p class="text-sm text-red-600 dark:text-red-400 text-center break-all">{{ errorMessage }}</p>
                  </div>
                </template>

              </div>

              <!-- Footer -->
              <div class="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                <template v-if="phase === 'idle'">
                  <button
                    @click="handleClose"
                    class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    @click="startFlash"
                    class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
                  >
                    Connect &amp; Flash
                  </button>
                </template>

                <template v-else-if="['downloading', 'connecting', 'flashing'].includes(phase)" />

                <template v-else-if="phase === 'done'">
                  <button
                    @click="handleClose"
                    class="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
                  >
                    Close
                  </button>
                </template>

                <template v-else-if="phase === 'error'">
                  <button
                    @click="handleClose"
                    class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    @click="reset"
                    class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
                  >
                    Try Again
                  </button>
                </template>
              </div>

            </div>
          </Transition>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
