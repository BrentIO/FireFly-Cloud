<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import {
  ArrowPathIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ClipboardDocumentIcon,
  ClipboardDocumentCheckIcon,
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
const showKeyModal    = ref(false)
const generatingKey   = ref(false)
const generatedKey    = ref(null)
const keyCopied       = ref(false)

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

// ── Registration key generation ───────────────────────────────────────────────
async function openKeyModal() {
  generatedKey.value = null
  keyCopied.value    = false
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
                @click="toggleSort('product_id')"
              >
                Product
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
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">
                Application
              </th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">
                MCU
              </th>
            </tr>
          </thead>

          <tbody>
            <!-- Loading skeleton -->
            <template v-if="loading">
              <tr v-for="i in 8" :key="i" class="border-b border-gray-100 dark:border-gray-800">
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-72" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-28" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-24" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-36" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-20" /></td>
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-else-if="paginatedDevices.length === 0">
              <td colspan="5" class="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                No registered devices found.
              </td>
            </tr>

            <!-- Data rows -->
            <tr
              v-else
              v-for="device in paginatedDevices"
              :key="device.uuid"
              class="border-b border-gray-100 dark:border-gray-800 odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800/50 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
            >
              <td class="px-4 py-3 font-mono text-xs text-gray-900 dark:text-gray-100 whitespace-nowrap">{{ device.uuid }}</td>
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="font-medium text-gray-900 dark:text-gray-100">{{ device.product_id }}</div>
                <div class="text-xs text-gray-400 dark:text-gray-500 font-mono">{{ device.product_hex }}</div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <RelativeTime :value="device.registration_date" />
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="text-gray-900 dark:text-gray-100">{{ device.registering_application }}</div>
                <div class="text-xs text-gray-400 dark:text-gray-500">{{ device.registering_version }}</div>
              </td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap text-xs font-mono">{{ device.mcu }}</td>
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

                <!-- Generating spinner -->
                <div v-if="generatingKey" class="flex items-center justify-center py-6">
                  <ArrowPathIcon class="w-8 h-8 text-blue-500 animate-spin" />
                </div>

                <!-- Key display -->
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
