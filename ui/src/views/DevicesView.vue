<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import {
  ArrowPathIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ClipboardDocumentIcon,
  ClipboardDocumentCheckIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import {
  Dialog,
  DialogPanel,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
import { useAuth } from '../composables/useAuth.js'
import { useToast } from '../composables/useToast.js'
import AppLayout from '../components/AppLayout.vue'
import RelativeTime from '../components/RelativeTime.vue'
import { listDevices, createRegistrationKey } from '../api/devices.js'

const { isSuperUser } = useAuth()
const { success: successToast, error: errorToast } = useToast()

const devices  = ref([])
const loading  = ref(true)

// ── Key modal ─────────────────────────────────────────────────────────────────
const showKeyModal  = ref(false)
const generatingKey = ref(false)
const generatedKey  = ref(null)
const keyCopied     = ref(false)

// ── Detail modal ──────────────────────────────────────────────────────────────
const selectedDevice   = ref(null)
const partitionHexSize = ref(new Set()) // indices of partition rows showing hex size
const showProductHex   = ref(false)

// ── Sort ──────────────────────────────────────────────────────────────────────
const sortKey = ref('registration_date')
const sortDir = ref('desc')

// ── Pagination ────────────────────────────────────────────────────────────────
const currentPage = ref(1)
const pageSize    = ref(10)

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const data = await listDevices()
    devices.value = data.devices
  } catch (e) {
    errorToast(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ── Sorting & pagination ──────────────────────────────────────────────────────
const sortedDevices = computed(() => {
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...devices.value].sort((a, b) => {
    const av = (a[sortKey.value] ?? '').toString().toLowerCase()
    const bv = (b[sortKey.value] ?? '').toString().toLowerCase()
    if (av < bv) return -1 * dir
    if (av > bv) return 1 * dir
    return 0
  })
})

const totalItems = computed(() => sortedDevices.value.length)
const totalPages = computed(() => Math.max(1, Math.ceil(totalItems.value / pageSize.value)))

const paginatedDevices = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return sortedDevices.value.slice(start, start + pageSize.value)
})

const showingFrom = computed(() =>
  totalItems.value === 0 ? 0 : (currentPage.value - 1) * pageSize.value + 1
)
const showingTo = computed(() =>
  Math.min(currentPage.value * pageSize.value, totalItems.value)
)

const pageNumbers = computed(() => {
  const total   = totalPages.value
  const current = currentPage.value
  if (total <= 5) return Array.from({ length: total }, (_, i) => i + 1)
  let start = Math.max(1, current - 2)
  let end   = start + 4
  if (end > total) { end = total; start = Math.max(1, end - 4) }
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

watch(pageSize, () => { currentPage.value = 1 })

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
  currentPage.value = 1
}

// ── Detail modal ──────────────────────────────────────────────────────────────
function openDetail(device) {
  selectedDevice.value = device
  partitionHexSize.value = new Set()
  showProductHex.value = false
}

function togglePartitionSize(i) {
  const s = new Set(partitionHexSize.value)
  s.has(i) ? s.delete(i) : s.add(i)
  partitionHexSize.value = s
}

// Formatting helpers
function formatDeviceClass(cls) {
  if (!cls) return '—'
  return cls.charAt(0).toUpperCase() + cls.slice(1).toLowerCase()
}

const INTERFACE_NAMES = {
  wifi:      'WiFi',
  wifi_ap:   'SoftAP',
  bluetooth: 'Bluetooth',
  ethernet:  'Ethernet',
}
function formatInterface(iface) {
  return INTERFACE_NAMES[iface?.toLowerCase()] ?? iface
}

const APP_SUBTYPES  = {
  0: 'Factory', 16: 'OTA_0', 17: 'OTA_1', 18: 'OTA_2', 19: 'OTA_3',
  20: 'OTA_4', 21: 'OTA_5', 22: 'OTA_6', 23: 'OTA_7', 24: 'OTA_8',
  25: 'OTA_9', 26: 'OTA_10', 27: 'OTA_11', 28: 'OTA_12', 29: 'OTA_13',
  30: 'OTA_14', 31: 'OTA_15', 32: 'Test',
}
const DATA_SUBTYPES = {
  0: 'OTA', 1: 'PHY', 2: 'NVS', 3: 'CoreDump', 4: 'NVS Keys',
  5: 'eFuse EM', 6: 'Undefined', 128: 'ESPHTTPD', 129: 'FAT',
  130: 'SPIFFS/LittleFS', 131: 'LittleFS',
}
const TYPE_NAMES = { 0: 'App', 1: 'Data', 2: 'Bootloader', 3: 'Partition Table' }

function formatPartitionType(type) {
  const name = TYPE_NAMES[type] ?? 'Unknown'
  return `${name} (0x${type.toString(16).padStart(2, '0').toUpperCase()})`
}
function formatPartitionSubtype(type, subtype) {
  const map = type === 0 ? APP_SUBTYPES : type === 1 ? DATA_SUBTYPES : {}
  const name = map[subtype]
  const hex  = `0x${subtype.toString(16).padStart(2, '0').toUpperCase()}`
  return name ? `${name} (${hex})` : hex
}
function formatPartitionSizeHuman(bytes) {
  if (bytes === undefined || bytes === null) return '—'
  return bytes >= 1048576
    ? `${(bytes / 1048576).toFixed(1)} MB`
    : `${(bytes / 1024).toFixed(1)} KB`
}
function formatPartitionSizeHex(bytes) {
  if (bytes === undefined || bytes === null) return '—'
  return `0x${bytes.toString(16).padStart(6, '0').toUpperCase()}`
}

function formatBytes(n) {
  if (!n && n !== 0) return '—'
  const mb = n / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(mb % 1 === 0 ? 0 : 1)} MB` : `${(n / 1024).toFixed(0)} KB`
}
function formatHz(n) {
  if (!n && n !== 0) return '—'
  return `${n / 1000000} MHz`
}
function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

// ── Registration key generation ───────────────────────────────────────────────
async function openKeyModal() {
  generatedKey.value  = null
  keyCopied.value     = false
  generatingKey.value = true
  showKeyModal.value  = true
  try {
    const data = await createRegistrationKey()
    generatedKey.value = data.key
  } catch (e) {
    showKeyModal.value = false
    errorToast(e.message)
  } finally {
    generatingKey.value = false
  }
}

async function copyKey() {
  if (!generatedKey.value) return
  try {
    await navigator.clipboard.writeText(generatedKey.value)
    keyCopied.value = true
    setTimeout(() => { keyCopied.value = false }, 2000)
  } catch {
    errorToast('Could not copy to clipboard.')
  }
}
</script>

<template>
  <AppLayout>
    <!-- Toolbar -->
    <div class="flex-shrink-0 flex items-center justify-between pb-4 flex-wrap gap-3">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Devices</h1>

      <div class="flex items-center gap-3">
        <button
          v-if="isSuperUser"
          @click="openKeyModal"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
        >
          Generate Registration Key
        </button>
        <button
          @click="load"
          :disabled="loading"
          class="rounded-md p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
          aria-label="Refresh"
        >
          <ArrowPathIcon class="w-5 h-5" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <!-- Table card -->
    <div class="flex flex-col flex-1 min-h-0 bg-white dark:bg-gray-900 rounded-xl shadow-sm ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
      <div class="flex-1 overflow-x-auto overflow-y-auto min-h-0">
        <table class="w-full text-sm">
          <thead class="sticky top-0 z-10">
            <tr class="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('uuid')"
              >
                UUID
                <ChevronUpIcon   v-if="sortKey === 'uuid' && sortDir === 'asc'"   class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'uuid' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('device_class')"
              >
                Device Class
                <ChevronUpIcon   v-if="sortKey === 'device_class' && sortDir === 'asc'"   class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'device_class' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('product_id')"
              >
                Product ID
                <ChevronUpIcon   v-if="sortKey === 'product_id' && sortDir === 'asc'"   class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'product_id' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('registration_date')"
              >
                Registered
                <ChevronUpIcon   v-if="sortKey === 'registration_date' && sortDir === 'asc'"   class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'registration_date' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
            </tr>
          </thead>

          <tbody>
            <!-- Loading skeleton -->
            <template v-if="loading">
              <tr v-for="i in 8" :key="i" class="border-b border-gray-100 dark:border-gray-800">
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-72" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-24" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-28" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-24" /></td>
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-else-if="paginatedDevices.length === 0">
              <td colspan="4" class="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                No registered devices found.
              </td>
            </tr>

            <!-- Data rows -->
            <tr
              v-else
              v-for="device in paginatedDevices"
              :key="device.uuid"
              class="border-b border-gray-100 dark:border-gray-800 odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800/50 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors cursor-pointer"
              @click="openDetail(device)"
            >
              <td class="px-4 py-3 font-mono text-xs text-gray-900 dark:text-gray-100 whitespace-nowrap">{{ device.uuid }}</td>
              <td class="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{{ formatDeviceClass(device.device_class) }}</td>
              <td class="px-4 py-3 text-gray-900 dark:text-gray-100 whitespace-nowrap">{{ device.product_id }}</td>
              <td class="px-4 py-3 whitespace-nowrap">
                <RelativeTime :value="device.registration_date" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div
        v-if="!loading"
        class="flex-shrink-0 flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex-wrap gap-3"
      >
        <p class="text-xs text-gray-500 dark:text-gray-400">
          Showing {{ showingFrom }}–{{ showingTo }} of {{ totalItems }} results
        </p>

        <div class="flex items-center gap-1">
          <button
            @click="currentPage = Math.max(1, currentPage - 1)"
            :disabled="currentPage === 1"
            class="px-2.5 py-1.5 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Previous
          </button>

          <button
            v-for="pg in pageNumbers"
            :key="pg"
            @click="currentPage = pg"
            class="min-w-[2rem] px-2.5 py-1.5 text-xs rounded border transition-colors"
            :class="pg === currentPage
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'"
          >
            {{ pg }}
          </button>

          <button
            @click="currentPage = Math.min(totalPages, currentPage + 1)"
            :disabled="currentPage === totalPages"
            class="px-2.5 py-1.5 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Next
          </button>
        </div>

        <div class="flex items-center gap-2">
          <label class="text-xs text-gray-500 dark:text-gray-400">Rows per page</label>
          <select
            v-model="pageSize"
            class="text-base sm:text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option :value="10">10</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Device detail modal -->
    <TransitionRoot :show="selectedDevice !== null" as="template">
      <Dialog as="div" class="relative z-50" @close="selectedDevice = null">
        <TransitionChild
          as="template"
          enter="ease-out duration-200" enter-from="opacity-0" enter-to="opacity-100"
          leave="ease-in duration-150" leave-from="opacity-100" leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50 transition-opacity" />
        </TransitionChild>

        <div class="fixed inset-0 z-10 overflow-y-auto p-4">
          <div class="flex min-h-full items-start justify-center pt-8">
            <TransitionChild
              as="template"
              enter="ease-out duration-200" enter-from="opacity-0 scale-95" enter-to="opacity-100 scale-100"
              leave="ease-in duration-150" leave-from="opacity-100 scale-100" leave-to="opacity-0 scale-95"
            >
              <DialogPanel
                v-if="selectedDevice"
                class="relative w-full max-w-2xl rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 divide-y divide-gray-100 dark:divide-gray-800"
                @click.stop
              >
                <!-- Header -->
                <div class="flex items-start justify-between px-6 py-4 gap-4">
                  <div class="min-w-0">
                    <h3 class="text-base font-semibold font-mono text-gray-900 dark:text-gray-100 break-all">{{ selectedDevice.uuid }}</h3>
                  </div>
                  <button
                    @click="selectedDevice = null"
                    class="flex-shrink-0 rounded-md p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    <XMarkIcon class="w-5 h-5" />
                  </button>
                </div>

                <!-- Identity -->
                <div class="px-6 py-4 space-y-3">
                  <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Identity</h4>
                  <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">Device Class</dt>
                      <dd class="text-gray-900 dark:text-gray-100">{{ formatDeviceClass(selectedDevice.device_class) }}</dd>
                    </div>
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">Product ID</dt>
                      <dd
                        class="cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 select-none"
                        :class="showProductHex ? 'font-mono text-gray-900 dark:text-gray-100' : 'text-gray-900 dark:text-gray-100'"
                        :title="showProductHex ? 'Click for Product ID' : 'Click for Product Hex'"
                        @click="showProductHex = !showProductHex"
                      >
                        {{ showProductHex ? selectedDevice.product_hex : selectedDevice.product_id }}
                      </dd>
                    </div>
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">Registered</dt>
                      <dd class="text-gray-900 dark:text-gray-100">{{ formatDate(selectedDevice.registration_date) }}</dd>
                    </div>
                    <div class="col-span-2">
                      <dt class="text-xs text-gray-500 dark:text-gray-400">Registering Application</dt>
                      <dd class="text-gray-900 dark:text-gray-100">{{ selectedDevice.registering_application }} <span class="text-gray-400 dark:text-gray-500">{{ selectedDevice.registering_version }}</span></dd>
                    </div>
                  </dl>
                </div>

                <!-- MCU -->
                <div v-if="selectedDevice.mcu" class="px-6 py-4 space-y-3">
                  <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">MCU</h4>
                  <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">Model</dt>
                      <dd class="font-mono text-gray-900 dark:text-gray-100">{{ selectedDevice.mcu.model ?? '—' }}</dd>
                    </div>
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">Revision</dt>
                      <dd class="text-gray-900 dark:text-gray-100">{{ selectedDevice.mcu.revision ?? '—' }}</dd>
                    </div>
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">CPU</dt>
                      <dd class="text-gray-900 dark:text-gray-100">{{ selectedDevice.mcu.cores ?? '—' }} cores @ {{ formatHz(selectedDevice.mcu.cpu_freq_mhz ? selectedDevice.mcu.cpu_freq_mhz * 1000000 : null) }}</dd>
                    </div>
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">IDF Version</dt>
                      <dd class="font-mono text-gray-900 dark:text-gray-100">{{ selectedDevice.mcu.idf_version ?? '—' }}</dd>
                    </div>
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">Flash</dt>
                      <dd class="text-gray-900 dark:text-gray-100">{{ formatBytes(selectedDevice.mcu.flash_chip_size) }} · {{ formatHz(selectedDevice.mcu.flash_chip_speed) }} · {{ selectedDevice.mcu.flash_chip_mode ?? '—' }}</dd>
                    </div>
                    <div>
                      <dt class="text-xs text-gray-500 dark:text-gray-400">PSRAM</dt>
                      <dd class="text-gray-900 dark:text-gray-100">{{ selectedDevice.mcu.psram_size ? formatBytes(selectedDevice.mcu.psram_size) : 'None' }}</dd>
                    </div>
                    <div v-if="selectedDevice.mcu.features?.length" class="col-span-2">
                      <dt class="text-xs text-gray-500 dark:text-gray-400 mb-1">Features</dt>
                      <dd class="flex flex-wrap gap-1">
                        <span
                          v-for="f in selectedDevice.mcu.features"
                          :key="f"
                          class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
                        >{{ f }}</span>
                      </dd>
                    </div>
                  </dl>
                </div>

                <!-- Network -->
                <div v-if="selectedDevice.network?.length" class="px-6 py-4 space-y-3">
                  <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Network</h4>
                  <table class="w-full text-sm">
                    <thead>
                      <tr class="text-left">
                        <th class="pb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 pr-6">Interface</th>
                        <th class="pb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">MAC Address</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
                      <tr v-for="iface in [...selectedDevice.network].sort((a, b) => formatInterface(a.interface).localeCompare(formatInterface(b.interface)))" :key="iface.interface">
                        <td class="py-1.5 pr-6 text-gray-700 dark:text-gray-300">{{ formatInterface(iface.interface) }}</td>
                        <td class="py-1.5 font-mono text-gray-900 dark:text-gray-100">{{ iface.mac_address }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Partitions -->
                <div v-if="selectedDevice.partitions?.length" class="px-6 py-4 space-y-3">
                  <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Partitions</h4>
                  <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                      <thead>
                        <tr class="text-left">
                          <th class="pb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 pr-4">Label</th>
                          <th class="pb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 pr-4">Type</th>
                          <th class="pb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 pr-4">Subtype</th>
                          <th class="pb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 pr-4">Address</th>
                          <th class="pb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">Size</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
                        <tr v-for="part in [...selectedDevice.partitions].sort((a, b) => a.address - b.address)" :key="part.address">
                          <td class="py-1.5 pr-4 font-mono text-gray-900 dark:text-gray-100">{{ part.label }}</td>
                          <td class="py-1.5 pr-4 text-gray-700 dark:text-gray-300 whitespace-nowrap">{{ formatPartitionType(part.type) }}</td>
                          <td class="py-1.5 pr-4 text-gray-700 dark:text-gray-300 whitespace-nowrap">{{ formatPartitionSubtype(part.type, part.subtype) }}</td>
                          <td class="py-1.5 pr-4 font-mono text-gray-700 dark:text-gray-300">{{ `0x${part.address.toString(16).padStart(6, '0').toUpperCase()}` }}</td>
                          <td
                            class="py-1.5 font-mono text-gray-700 dark:text-gray-300 cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 select-none"
                            :title="partitionHexSize.has(part.address) ? 'Click for human-readable' : 'Click for hex'"
                            @click="togglePartitionSize(part.address)"
                          >
                            {{ partitionHexSize.has(part.address) ? formatPartitionSizeHex(part.size) : formatPartitionSizeHuman(part.size) }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- Footer -->
                <div class="px-6 py-4 flex justify-end">
                  <button
                    @click="selectedDevice = null"
                    class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    Close
                  </button>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>

    <!-- Registration key modal -->
    <TransitionRoot :show="showKeyModal" as="template">
      <Dialog as="div" class="relative z-50" @close="showKeyModal = false">
        <TransitionChild
          as="template"
          enter="ease-out duration-200" enter-from="opacity-0" enter-to="opacity-100"
          leave="ease-in duration-150" leave-from="opacity-100" leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50 transition-opacity" />
        </TransitionChild>

        <div class="fixed inset-0 z-10 overflow-y-auto" @click="showKeyModal = false">
          <div class="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as="template"
              enter="ease-out duration-200" enter-from="opacity-0 scale-95" enter-to="opacity-100 scale-100"
              leave="ease-in duration-150" leave-from="opacity-100 scale-100" leave-to="opacity-0 scale-95"
            >
              <DialogPanel
                class="relative w-full max-w-sm rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 p-6 space-y-5"
                @click.stop
              >
                <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">Registration Key</h3>

                <div v-if="generatingKey" class="flex items-center justify-center py-6">
                  <ArrowPathIcon class="w-8 h-8 text-blue-500 animate-spin" />
                </div>

                <template v-else-if="generatedKey">
                  <div class="flex items-center gap-3">
                    <span class="flex-1 text-center text-4xl font-mono font-bold tracking-widest text-gray-900 dark:text-gray-100 bg-gray-100 dark:bg-gray-800 rounded-lg py-4 select-all">
                      {{ generatedKey }}
                    </span>
                    <button
                      @click="copyKey"
                      class="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                      :aria-label="keyCopied ? 'Copied' : 'Copy to clipboard'"
                    >
                      <ClipboardDocumentCheckIcon v-if="keyCopied" class="w-6 h-6 text-green-500" />
                      <ClipboardDocumentIcon v-else class="w-6 h-6" />
                    </button>
                  </div>

                  <p class="text-xs text-gray-500 dark:text-gray-400">
                    This key expires in 30 minutes. Enter it in the HW-Reg Registration screen on the device being registered. Each key can only be used once.
                  </p>
                </template>

                <div class="flex justify-end">
                  <button
                    @click="showKeyModal = false"
                    class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    Close
                  </button>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>
  </AppLayout>
</template>
