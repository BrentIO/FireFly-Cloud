<script setup>
import { ref, computed, onUnmounted } from 'vue'
import {
  Dialog,
  DialogPanel,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
import {
  XMarkIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/vue/24/outline'
import { ESPLoader, Transport } from 'esptool-js'
import JSZip from 'jszip'
import SparkMD5 from 'spark-md5'
import { getFirmwareDownloadUrl } from '../api/firmware.js'

const props = defineProps({
  open: { type: Boolean, required: true },
  item: { type: Object, required: true },
  zipName: { type: String, required: true },
})

const emit = defineEmits(['close'])

// phase: idle | downloading | connecting | flashing | done | error
const phase = ref('idle')
const statusMessage = ref('')
const errorMessage = ref('')
const chipName = ref('')
const fileProgress = ref([]) // [{ name, address, written, total }]

let transport = null

// ---------------------------------------------------------------------------
// Flash address table derived from FireFly partition layout:
//   bootloader  → 0x01000
//   application → 0x10000  (app0 partition)
//   config      → 0xC90000
//   www         → 0xD10000
//   partitions  → skipped (device-specific; do not overwrite)
// ---------------------------------------------------------------------------
function resolveFlashAddress(filename) {
  if (filename.endsWith('.partitions.bin')) return null
  if (filename.endsWith('.bootloader.bin')) return 0x01000
  if (filename === 'config.bin') return 0xC90000
  if (filename === 'www.bin') return 0xD10000
  if (filename.endsWith('.bin')) return 0x10000
  return null
}

function formatAddress(addr) {
  return '0x' + addr.toString(16).toUpperCase().padStart(5, '0')
}

const flashableFiles = computed(() =>
  (props.item.files || [])
    .map(f => ({ name: f.name, address: resolveFlashAddress(f.name) }))
    .filter(f => f.address !== null)
    .sort((a, b) => a.address - b.address)
)

const skippedFiles = computed(() =>
  (props.item.files || []).filter(f => resolveFlashAddress(f.name) === null)
)

// ---------------------------------------------------------------------------
// Flash sequence
// ---------------------------------------------------------------------------
async function startFlash() {
  phase.value = 'downloading'
  errorMessage.value = ''
  chipName.value = ''
  fileProgress.value = flashableFiles.value.map(f => ({
    name: f.name,
    address: f.address,
    written: 0,
    total: 0,
  }))

  try {
    // 1. Fetch pre-signed URL and download ZIP
    statusMessage.value = 'Fetching download URL…'
    const { url } = await getFirmwareDownloadUrl(props.zipName)

    statusMessage.value = 'Downloading firmware ZIP…'
    const response = await fetch(url)
    if (!response.ok) throw new Error(`Download failed (HTTP ${response.status})`)
    const zipBuffer = await response.arrayBuffer()

    // 2. Extract binary files from ZIP
    statusMessage.value = 'Extracting firmware files…'
    const zip = await JSZip.loadAsync(zipBuffer)
    const fileArray = []
    for (const f of flashableFiles.value) {
      const entry = zip.file(f.name)
      if (!entry) throw new Error(`File not found in ZIP: ${f.name}`)
      const data = await entry.async('binary')
      fileArray.push({ data, address: f.address })
    }

    // 3. Request Web Serial port (opens browser picker)
    phase.value = 'connecting'
    statusMessage.value = 'Waiting for port selection…'
    const port = await navigator.serial.requestPort()

    // 4. Connect via esptool-js
    transport = new Transport(port, false)
    const terminal = { clean() {}, writeLine() {}, write() {} }
    const esploader = new ESPLoader({ transport, baudrate: 921600, terminal })

    statusMessage.value = 'Connecting to device…'
    const chip = await esploader.main()
    chipName.value = chip || 'ESP32'

    // 5. Flash
    phase.value = 'flashing'
    await esploader.write_flash({
      fileArray,
      flashSize: 'keep',
      flashMode: 'keep',
      flashFreq: 'keep',
      eraseAll: false,
      compress: true,
      reportProgress(fileIndex, written, total) {
        if (fileProgress.value[fileIndex]) {
          fileProgress.value[fileIndex].written = written
          fileProgress.value[fileIndex].total = total
        }
      },
      calculateMD5Hash(image) {
        return SparkMD5.hash(image, false)
      },
    })

    phase.value = 'done'
  } catch (err) {
    // User cancelling the port picker throws a DOMException with name NotAllowedError
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
  fileProgress.value = []
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
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-60" @close="handleClose">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-150"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/60 transition-opacity" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-200"
            enter-from="opacity-0 scale-95"
            enter-to="opacity-100 scale-100"
            leave="ease-in duration-150"
            leave-from="opacity-100 scale-100"
            leave-to="opacity-0 scale-95"
          >
            <DialogPanel
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

                  <!-- Files to flash -->
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
                          v-for="f in flashableFiles"
                          :key="f.name"
                          class="bg-white dark:bg-gray-900"
                        >
                          <td class="px-4 py-2 font-mono text-xs text-gray-900 dark:text-gray-100">{{ f.name }}</td>
                          <td class="px-4 py-2 font-mono text-xs text-right text-gray-500 dark:text-gray-400">{{ formatAddress(f.address) }}</td>
                        </tr>
                        <tr
                          v-for="f in skippedFiles"
                          :key="f.name"
                          class="bg-white dark:bg-gray-900"
                        >
                          <td class="px-4 py-2 font-mono text-xs text-gray-400 dark:text-gray-600">{{ f.name }}</td>
                          <td class="px-4 py-2 text-xs text-right text-gray-400 dark:text-gray-600 italic">skipped</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <p class="text-xs text-gray-500 dark:text-gray-400">
                    If your device does not reset automatically, hold the
                    <strong>BOOT</strong> button while pressing <strong>EN</strong> to enter bootloader mode before connecting.
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
                  <div class="space-y-3">
                    <div v-for="(f, i) in fileProgress" :key="f.name">
                      <div class="flex items-center justify-between mb-1">
                        <span class="font-mono text-xs text-gray-700 dark:text-gray-300">{{ f.name }}</span>
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
                <!-- Idle -->
                <template v-if="phase === 'idle'">
                  <button
                    @click="handleClose"
                    class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    @click="startFlash"
                    :disabled="flashableFiles.length === 0"
                    class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                  >
                    Connect &amp; Flash
                  </button>
                </template>

                <!-- Downloading / Connecting / Flashing: no actions -->
                <template v-else-if="['downloading', 'connecting', 'flashing'].includes(phase)" />

                <!-- Done -->
                <template v-else-if="phase === 'done'">
                  <button
                    @click="handleClose"
                    class="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
                  >
                    Close
                  </button>
                </template>

                <!-- Error -->
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

            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
