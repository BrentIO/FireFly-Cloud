<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Menu,
  MenuButton,
  MenuItems,
  MenuItem,
} from '@headlessui/vue'
import {
  ArrowPathIcon,
  EllipsisVerticalIcon,
  ChevronUpIcon,
  ChevronDownIcon,
} from '@heroicons/vue/24/outline'
import AppLayout from '../components/AppLayout.vue'
import StatusBadge from '../components/StatusBadge.vue'
import FirmwareDetailModal from '../components/FirmwareDetailModal.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import { listFirmware, patchFirmwareStatus, deleteFirmware } from '../api/firmware.js'
import { useToast } from '../composables/useToast.js'
import {
  VALID_TRANSITIONS,
  ROLLBACK_TRANSITIONS,
  TRANSITION_BUTTON_LABELS,
  TRANSITIONS_REQUIRING_CONFIRM,
  NON_DELETABLE_STATES,
} from '../utils/formatters.js'

const route = useRoute()
const router = useRouter()
const { success, error } = useToast()

// ── Data ──────────────────────────────────────────────────────────────────────
const allItems = ref([])
const loading = ref(false)

// ── Toolbar toggles ───────────────────────────────────────────────────────────
const showDeleted = ref(false)
const showReleased = ref(false)

// ── Text filters ──────────────────────────────────────────────────────────────
const filterApplication = ref('')
const filterProductId = ref('')
const filterVersion = ref('')

// ── Sort ──────────────────────────────────────────────────────────────────────
const sortKey = ref('uploaded_at')
const sortDir = ref('desc')

// ── Pagination ────────────────────────────────────────────────────────────────
const currentPage = ref(1)
const pageSize = ref(10)

// ── Confirm modal ─────────────────────────────────────────────────────────────
const confirmOpen = ref(false)
const confirmTitle = ref('')
const confirmMessage = ref('')
const confirmDetails = ref(null)
const confirmVariant = ref('danger')
const confirmAction = ref(null)

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function fetchFirmware() {
  loading.value = true
  try {
    const data = await listFirmware()
    allItems.value = data.items || []
  } catch (err) {
    error('Failed to load firmware list.', err)
  } finally {
    loading.value = false
  }
}

onMounted(fetchFirmware)

// ── Filtering & sorting ───────────────────────────────────────────────────────
const filteredItems = computed(() => {
  let items = allItems.value

  if (!showDeleted.value) {
    items = items.filter((i) => i.release_status !== 'DELETED')
  }
  if (!showReleased.value) {
    items = items.filter((i) => i.release_status !== 'RELEASED')
  }
  if (filterApplication.value.trim()) {
    const q = filterApplication.value.trim().toLowerCase()
    items = items.filter((i) => i.application?.toLowerCase().includes(q))
  }
  if (filterProductId.value.trim()) {
    const q = filterProductId.value.trim().toLowerCase()
    items = items.filter((i) => i.product_id?.toLowerCase().includes(q))
  }
  if (filterVersion.value.trim()) {
    const q = filterVersion.value.trim().toLowerCase()
    items = items.filter((i) => i.version?.toLowerCase().includes(q))
  }

  // Sort
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  items = [...items].sort((a, b) => {
    const av = a[key] ?? ''
    const bv = b[key] ?? ''
    if (av < bv) return -1 * dir
    if (av > bv) return 1 * dir
    return 0
  })

  return items
})

const totalItems = computed(() => filteredItems.value.length)
const totalPages = computed(() => Math.max(1, Math.ceil(totalItems.value / pageSize.value)))

const paginatedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredItems.value.slice(start, start + pageSize.value)
})

const showingFrom = computed(() =>
  totalItems.value === 0 ? 0 : (currentPage.value - 1) * pageSize.value + 1
)
const showingTo = computed(() =>
  Math.min(currentPage.value * pageSize.value, totalItems.value)
)

// Page numbers to display (up to 5)
const pageNumbers = computed(() => {
  const total = totalPages.value
  const current = currentPage.value
  if (total <= 5) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  let start = Math.max(1, current - 2)
  let end = start + 4
  if (end > total) {
    end = total
    start = Math.max(1, end - 4)
  }
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

// Reset to page 1 when filters change
watch(
  [showDeleted, showReleased, filterApplication, filterProductId, filterVersion, pageSize],
  () => {
    currentPage.value = 1
  }
)

// ── Sort toggle ───────────────────────────────────────────────────────────────
function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

// ── Row navigation ────────────────────────────────────────────────────────────
function goToDetail(item) {
  router.push(`/firmware/${encodeURIComponent(item.zip_name)}`)
}

// ── Status transition from ellipsis menu ─────────────────────────────────────
function requestMenuTransition(item, nextStatus) {
  if (TRANSITIONS_REQUIRING_CONFIRM.has(nextStatus)) {
    confirmTitle.value = `Confirm: ${TRANSITION_BUTTON_LABELS[nextStatus]}`
    confirmMessage.value = `Are you sure you want to move this firmware to ${nextStatus}?`
    confirmDetails.value = nextStatus === 'RELEASED' ? {
      Application: item.application,
      'Product ID': item.product_id,
      Branch: item.branch,
      Commit: item.commit,
    } : null
    confirmVariant.value = nextStatus === 'RELEASED' ? 'success' : 'danger'
    confirmAction.value = () => executeMenuTransition(item, nextStatus)
    confirmOpen.value = true
  } else {
    executeMenuTransition(item, nextStatus)
  }
}

async function executeMenuTransition(item, nextStatus) {
  confirmOpen.value = false
  try {
    await patchFirmwareStatus(item.zip_name, nextStatus)
    success(`Status updated to ${nextStatus}.`)
    await fetchFirmware()
  } catch (err) {
    error(`Failed to update status: ${err.message}`, err)
  }
}

// ── Delete from ellipsis menu ─────────────────────────────────────────────────
function requestMenuDelete(item) {
  confirmTitle.value = 'Confirm Delete'
  confirmMessage.value = 'Are you sure you want to delete this firmware? This action cannot be undone.'
  confirmDetails.value = {
    Application: item.application,
    Version: item.version,
    Branch: item.branch,
    Commit: item.commit,
    'ZIP Name': item.zip_name,
  }
  confirmAction.value = () => executeMenuDelete(item)
  confirmOpen.value = true
}

async function executeMenuDelete(item) {
  confirmOpen.value = false
  try {
    await deleteFirmware(item.zip_name)
    success('Firmware deletion initiated.')
    await fetchFirmware()
  } catch (err) {
    error(`Failed to delete firmware: ${err.message}`, err)
  }
}

function handleConfirm() {
  if (confirmAction.value) confirmAction.value()
}

function handleConfirmCancel() {
  confirmOpen.value = false
  confirmAction.value = null
}

// ── Detail modal ──────────────────────────────────────────────────────────────
const detailZipName = computed(() => route.params.zip_name || null)

function closeDetail() {
  router.push('/firmware')
}

async function onDetailChanged() {
  await fetchFirmware()
}
</script>

<template>
  <AppLayout>
    <!-- Toolbar -->
    <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Firmware</h1>

      <div class="flex items-center gap-4 flex-wrap">
        <!-- Show Deleted toggle -->
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <span class="text-sm text-gray-600 dark:text-gray-400">Show Deleted</span>
          <button
            type="button"
            role="switch"
            :aria-checked="showDeleted"
            @click="showDeleted = !showDeleted"
            class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
            :class="showDeleted ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'"
          >
            <span
              class="inline-block h-3.5 w-3.5 rounded-full bg-white shadow transform transition-transform"
              :class="showDeleted ? 'translate-x-4.5' : 'translate-x-0.5'"
            />
          </button>
        </label>

        <!-- Show Released toggle -->
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <span class="text-sm text-gray-600 dark:text-gray-400">Show Released</span>
          <button
            type="button"
            role="switch"
            :aria-checked="showReleased"
            @click="showReleased = !showReleased"
            class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
            :class="showReleased ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'"
          >
            <span
              class="inline-block h-3.5 w-3.5 rounded-full bg-white shadow transform transition-transform"
              :class="showReleased ? 'translate-x-4.5' : 'translate-x-0.5'"
            />
          </button>
        </label>

        <!-- Refresh -->
        <button
          @click="fetchFirmware"
          :disabled="loading"
          class="rounded-md p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
          aria-label="Refresh"
        >
          <ArrowPathIcon class="w-5 h-5" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <!-- Table card -->
    <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm ring-1 ring-black/5 dark:ring-white/10">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <!-- Filter row -->
            <tr class="border-b border-gray-200 dark:border-gray-700">
              <td class="px-4 py-2">
                <input
                  v-model="filterApplication"
                  type="text"
                  placeholder="Filter…"
                  class="w-full text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </td>
              <td class="px-4 py-2">
                <input
                  v-model="filterProductId"
                  type="text"
                  placeholder="Filter…"
                  class="w-full text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </td>
              <td class="px-4 py-2">
                <input
                  v-model="filterVersion"
                  type="text"
                  placeholder="Filter…"
                  class="w-full text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </td>
              <td class="px-4 py-2"></td>
              <td class="px-4 py-2"></td>
            </tr>
            <!-- Column header row -->
            <tr class="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('application')"
              >
                Application
                <ChevronUpIcon v-if="sortKey === 'application' && sortDir === 'asc'" class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'application' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('product_id')"
              >
                Product ID
                <ChevronUpIcon v-if="sortKey === 'product_id' && sortDir === 'asc'" class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'product_id' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('version')"
              >
                Version
                <ChevronUpIcon v-if="sortKey === 'version' && sortDir === 'asc'" class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'version' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('release_status')"
              >
                Release Status
                <ChevronUpIcon v-if="sortKey === 'release_status' && sortDir === 'asc'" class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'release_status' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>

          <tbody>
            <!-- Loading skeleton -->
            <template v-if="loading">
              <tr
                v-for="i in 8"
                :key="i"
                class="border-b border-gray-100 dark:border-gray-800"
              >
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-24" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-28" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-20" /></td>
                <td class="px-4 py-3"><div class="h-5 bg-gray-200 dark:bg-gray-700 rounded-full animate-pulse w-20" /></td>
                <td class="px-4 py-3"></td>
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-else-if="paginatedItems.length === 0">
              <td colspan="5" class="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                No firmware records found.
              </td>
            </tr>

            <!-- Data rows -->
            <tr
              v-else
              v-for="(item, index) in paginatedItems"
              :key="item.zip_name"
              class="border-b border-gray-100 dark:border-gray-800 cursor-pointer transition-colors odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800/50 hover:bg-blue-50 dark:hover:bg-blue-900/20"
              @click.self="goToDetail(item)"
            >
              <td class="px-4 py-3 font-medium text-gray-900 dark:text-gray-100" @click="goToDetail(item)">
                {{ item.application }}
              </td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400" @click="goToDetail(item)">
                {{ item.product_id }}
              </td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400" @click="goToDetail(item)">
                {{ item.version }}
              </td>
              <td class="px-4 py-3" @click="goToDetail(item)">
                <StatusBadge :status="item.release_status" />
              </td>

              <!-- Actions ellipsis menu -->
              <td class="px-4 py-3 text-right" @click.stop>
                <Menu as="div" class="relative inline-block text-left">
                  <MenuButton
                    class="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    aria-label="Actions"
                  >
                    <EllipsisVerticalIcon class="w-5 h-5" />
                  </MenuButton>

                  <MenuItems
                    :class="[
                      'absolute right-0 z-50 w-48 rounded-lg bg-white dark:bg-gray-800 shadow-lg ring-1 ring-black/10 dark:ring-white/10 focus:outline-none divide-y divide-gray-100 dark:divide-gray-700',
                      index >= paginatedItems.length - 2 ? 'bottom-full mb-1 origin-bottom-right' : 'mt-1 origin-top-right',
                    ]"
                  >
                    <!-- Details -->
                    <div class="py-1">
                      <MenuItem v-slot="{ active }">
                        <button
                          @click="goToDetail(item)"
                          class="w-full text-left px-4 py-2 text-sm transition-colors"
                          :class="active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'"
                        >
                          Details
                        </button>
                      </MenuItem>
                    </div>

                    <!-- Rollback transition -->
                    <div v-if="ROLLBACK_TRANSITIONS[item.release_status]" class="py-1">
                      <MenuItem v-slot="{ active }">
                        <button
                          @click="requestMenuTransition(item, ROLLBACK_TRANSITIONS[item.release_status])"
                          class="w-full text-left px-4 py-2 text-sm transition-colors"
                          :class="active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'"
                        >
                          {{ TRANSITION_BUTTON_LABELS[ROLLBACK_TRANSITIONS[item.release_status]] }}
                        </button>
                      </MenuItem>
                    </div>

                    <!-- Forward transition actions -->
                    <div v-if="VALID_TRANSITIONS[item.release_status]" class="py-1">
                      <MenuItem v-slot="{ active }">
                        <button
                          @click="requestMenuTransition(item, VALID_TRANSITIONS[item.release_status])"
                          class="w-full text-left px-4 py-2 text-sm transition-colors"
                          :class="active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'"
                        >
                          {{ TRANSITION_BUTTON_LABELS[VALID_TRANSITIONS[item.release_status]] }}
                        </button>
                      </MenuItem>
                    </div>

                    <!-- Delete -->
                    <div v-if="!NON_DELETABLE_STATES.has(item.release_status)" class="py-1">
                      <MenuItem v-slot="{ active }">
                        <button
                          @click="requestMenuDelete(item)"
                          class="w-full text-left px-4 py-2 text-sm transition-colors"
                          :class="active ? 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400' : 'text-red-600 dark:text-red-400'"
                        >
                          Delete
                        </button>
                      </MenuItem>
                    </div>
                  </MenuItems>
                </Menu>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div
        v-if="!loading"
        class="flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex-wrap gap-3"
      >
        <!-- Showing X–Y of Z -->
        <p class="text-xs text-gray-500 dark:text-gray-400">
          Showing {{ showingFrom }}–{{ showingTo }} of {{ totalItems }} results
        </p>

        <!-- Page buttons -->
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
            :class="
              pg === currentPage
                ? 'bg-blue-600 border-blue-600 text-white'
                : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
            "
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

        <!-- Rows per page -->
        <div class="flex items-center gap-2">
          <label class="text-xs text-gray-500 dark:text-gray-400">Rows per page</label>
          <select
            v-model="pageSize"
            class="text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option :value="10">10</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <FirmwareDetailModal
      v-if="detailZipName"
      :zip-name="detailZipName"
      @close="closeDetail"
      @changed="onDetailChanged"
    />

    <!-- Confirm Modal -->
    <ConfirmModal
      :open="confirmOpen"
      :title="confirmTitle"
      :message="confirmMessage"
      :details="confirmDetails"
      :variant="confirmVariant"
      @confirm="handleConfirm"
      @cancel="handleConfirmCancel"
    />
  </AppLayout>
</template>
