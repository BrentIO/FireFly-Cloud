<script setup>
import { ref, computed, watch } from 'vue'
import {
  Dialog,
  DialogPanel,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
import {
  XMarkIcon,
  ArrowDownTrayIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  BoltIcon,
} from '@heroicons/vue/24/outline'
import StatusBadge from './StatusBadge.vue'
import RelativeTime from './RelativeTime.vue'
import ConfirmModal from './ConfirmModal.vue'
import FirmwareFlashModal from './FirmwareFlashModal.vue'
import { getFirmware, patchFirmwareStatus, deleteFirmware, getFirmwareDownloadUrl } from '../api/firmware.js'
import { useToast } from '../composables/useToast.js'
import {
  formatBytes,
  formatClass,
  formatAbsoluteDate,
  STATUS_LABELS,
  VALID_TRANSITIONS,
  ROLLBACK_TRANSITIONS,
  TRANSITION_BUTTON_LABELS,
  TRANSITIONS_REQUIRING_CONFIRM,
  NON_DELETABLE_STATES,
} from '../utils/formatters.js'

const props = defineProps({
  zipName: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['close', 'changed'])

const { success, error } = useToast()

const item = ref(null)
const loading = ref(false)
const loadError = ref(null)

// Download state
const downloadLoading = ref(false)

// Flash modal state
const flashOpen = ref(false)
const webSerialSupported = 'serial' in navigator

// True when the firmware record has a non-empty partition_offsets map (required for Flash via USB)
const hasPartitionOffsets = computed(() => {
  const offsets = item.value?.partition_offsets
  return offsets != null && Object.keys(offsets).length > 0
})

// Manifest files disclosure
const manifestOpen = ref(false)

// Confirm modal state
const confirmOpen = ref(false)
const confirmTitle = ref('')
const confirmMessage = ref('')
const confirmDetails = ref(null)
const confirmVariant = ref('danger')
const confirmLabel = ref('Confirm')
const confirmAction = ref(null)

async function loadItem() {
  loading.value = true
  loadError.value = null
  item.value = null
  try {
    item.value = await getFirmware(props.zipName)
  } catch (err) {
    loadError.value = err.message || 'Failed to load firmware details.'
    error('Failed to load firmware details.', err)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.zipName,
  (val) => {
    if (val) loadItem()
  },
  { immediate: true }
)

async function handleDownload() {
  downloadLoading.value = true
  try {
    const data = await getFirmwareDownloadUrl(props.zipName)
    window.open(data.url, '_blank')
  } catch (err) {
    error('Failed to get download URL.', err)
  } finally {
    downloadLoading.value = false
  }
}

function requestTransition(nextStatus) {
  if (TRANSITIONS_REQUIRING_CONFIRM.has(nextStatus)) {
    confirmTitle.value = `Confirm: ${TRANSITION_BUTTON_LABELS[nextStatus]}`
    confirmMessage.value = `Are you sure you want to move this firmware to ${nextStatus}?`
    confirmDetails.value = nextStatus === 'RELEASED' ? {
      Application: item.value.application,
      'Product ID': item.value.product_id,
      Branch: item.value.branch,
      Commit: item.value.commit,
    } : null
    confirmVariant.value = nextStatus === 'RELEASED' ? 'success' : 'danger'
    confirmLabel.value = TRANSITION_BUTTON_LABELS[nextStatus] || 'Confirm'
    confirmAction.value = () => executeTransition(nextStatus)
    confirmOpen.value = true
  } else {
    executeTransition(nextStatus)
  }
}

async function executeTransition(nextStatus) {
  confirmOpen.value = false
  try {
    await patchFirmwareStatus(props.zipName, nextStatus)
    success(`Status updated to ${STATUS_LABELS[nextStatus] || nextStatus}.`)
    await loadItem()
    emit('changed')
  } catch (err) {
    error(`Failed to update status: ${err.message}`, err)
  }
}

function requestDelete() {
  confirmTitle.value = 'Confirm Delete'
  confirmMessage.value = 'Are you sure you want to delete this firmware? This action cannot be undone.'
  confirmDetails.value = {
    Application: item.value.application,
    Version: item.value.version,
    Branch: item.value.branch,
    Commit: item.value.commit,
    'ZIP Name': item.value.zip_name,
  }
  confirmVariant.value = 'danger'
  confirmLabel.value = 'Delete'
  confirmAction.value = () => executeDelete()
  confirmOpen.value = true
}

async function executeDelete() {
  confirmOpen.value = false
  try {
    await deleteFirmware(props.zipName)
    success('Firmware deletion initiated.')
    emit('changed')
    emit('close')
  } catch (err) {
    error(`Failed to delete firmware: ${err.message}`, err)
  }
}

function handleConfirm() {
  if (confirmAction.value) confirmAction.value()
}

function handleCancel() {
  confirmOpen.value = false
  confirmAction.value = null
}

function transitionButtonClass(nextStatus) {
  if (nextStatus === 'TESTING') return 'px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors'
  if (nextStatus === 'RELEASED') return 'px-3 py-1.5 text-sm font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white transition-colors'
  if (nextStatus === 'REVOKED') return 'px-3 py-1.5 text-sm font-medium rounded-lg bg-orange-600 hover:bg-orange-700 text-white transition-colors'
  return 'px-3 py-1.5 text-sm font-medium rounded-lg bg-gray-600 hover:bg-gray-700 text-white transition-colors'
}
</script>

<template>
  <TransitionRoot :show="true" as="template">
    <Dialog as="div" class="relative z-50" @close="() => {}">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-150"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/50 transition-opacity" />
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
              class="relative w-full max-w-2xl rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 overflow-hidden"
            >
              <!-- Loading skeleton -->
              <div v-if="loading" class="p-6 space-y-4">
                <div class="flex justify-end">
                  <button
                    @click="emit('close')"
                    class="rounded-md p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    aria-label="Close"
                  >
                    <XMarkIcon class="w-5 h-5" />
                  </button>
                </div>
                <div class="h-6 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-1/2" />
                <div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-1/4" />
                <div class="grid grid-cols-2 gap-4 mt-4">
                  <div v-for="i in 8" :key="i" class="space-y-1.5">
                    <div class="h-3 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-1/3" />
                    <div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-2/3" />
                  </div>
                </div>
              </div>

              <!-- Error state -->
              <div v-else-if="loadError" class="p-6">
                <p class="text-sm text-red-600 dark:text-red-400">{{ loadError }}</p>
                <button
                  @click="emit('close')"
                  class="mt-4 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  Close
                </button>
              </div>

              <!-- Content -->
              <div v-else-if="item" class="flex flex-col max-h-[90vh]">
                <!-- Header -->
                <div class="flex items-start justify-between p-6 pb-4 border-b border-gray-200 dark:border-gray-700">
                  <div class="flex flex-col gap-1">
                    <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {{ item.product_id }} ({{ formatClass(item.class) }}) &mdash; {{ item.branch }}
                    </h2>
                    <p class="text-sm text-gray-500 dark:text-gray-400">
                      {{ item.application }}
                    </p>
                  </div>
                  <button
                    @click="emit('close')"
                    class="ml-4 flex-shrink-0 rounded-md p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    aria-label="Close"
                  >
                    <XMarkIcon class="w-5 h-5" />
                  </button>
                </div>

                <!-- Scrollable body -->
                <div class="overflow-y-auto p-6 space-y-6">
                  <!-- Fields grid -->
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
                    <!-- Application -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Application</p>
                      <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ item.application }}</p>
                    </div>

                    <!-- Product ID + Class -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Product ID</p>
                      <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {{ item.product_id }} ({{ formatClass(item.class) }})
                      </p>
                    </div>

                    <!-- Branch -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Branch</p>
                      <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ item.branch }}</p>
                    </div>

                    <!-- Commit -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Commit</p>
                      <p class="text-sm font-medium font-mono truncate text-gray-900 dark:text-gray-100">{{ item.commit }}</p>
                    </div>

                    <!-- Created Date -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Created</p>
                      <RelativeTime :value="item.created" />
                    </div>

                    <!-- Uploaded -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Uploaded</p>
                      <RelativeTime v-if="item.uploaded_at" :value="item.uploaded_at" />
                      <p v-else class="text-sm text-gray-400 dark:text-gray-500">—</p>
                    </div>

                    <!-- ZIP Name -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">ZIP Name</p>
                      <p class="text-xs font-mono text-gray-900 dark:text-gray-100 break-all">{{ item.zip_name }}</p>
                    </div>

                    <!-- ZIP Size -->
                    <div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">ZIP Size</p>
                      <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ formatBytes(item.zip_size) }}</p>
                    </div>

                    <!-- Release Status + transitions -->
                    <div class="sm:col-span-2">
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-1">Release Status</p>
                      <div class="flex items-center gap-3 flex-wrap">
                        <StatusBadge :status="item.release_status" />
                        <button
                          v-if="ROLLBACK_TRANSITIONS[item.release_status]"
                          @click="requestTransition(ROLLBACK_TRANSITIONS[item.release_status])"
                          class="px-3 py-1.5 text-sm font-medium rounded-lg bg-gray-600 hover:bg-gray-700 text-white transition-colors"
                        >
                          {{ TRANSITION_BUTTON_LABELS[ROLLBACK_TRANSITIONS[item.release_status]] }}
                        </button>
                        <button
                          v-if="VALID_TRANSITIONS[item.release_status]"
                          @click="requestTransition(VALID_TRANSITIONS[item.release_status])"
                          :class="transitionButtonClass(VALID_TRANSITIONS[item.release_status])"
                        >
                          {{ TRANSITION_BUTTON_LABELS[VALID_TRANSITIONS[item.release_status]] }}
                        </button>
                      </div>
                    </div>

                    <!-- Error message -->
                    <div v-if="item.error" class="sm:col-span-2">
                      <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">Error</p>
                      <p class="text-sm text-red-600 dark:text-red-400">{{ item.error }}</p>
                    </div>
                  </div>

                  <!-- TTL info box -->
                  <div
                    v-if="item.ttl"
                    class="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
                  >
                    This record will be automatically purged on {{ formatAbsoluteDate(item.ttl) }}.
                  </div>

                  <!-- Manifest files disclosure -->
                  <div
                    v-if="item.files && item.files.length"
                    class="border-t border-gray-200 dark:border-gray-700 pt-4"
                  >
                    <button
                      @click="manifestOpen = !manifestOpen"
                      class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
                    >
                      <ChevronUpIcon v-if="manifestOpen" class="w-4 h-4" />
                      <ChevronDownIcon v-else class="w-4 h-4" />
                      Manifest Files ({{ item.files.length }})
                    </button>

                    <div v-if="manifestOpen" class="mt-3 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                      <table class="w-full text-sm">
                        <thead class="bg-gray-50 dark:bg-gray-800">
                          <tr>
                            <th class="text-left px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">File Name</th>
                            <th class="text-left px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">SHA-256</th>
                          </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
                          <tr
                            v-for="file in item.files"
                            :key="file.name"
                            class="bg-white dark:bg-gray-900"
                          >
                            <td class="px-4 py-2 font-mono text-xs text-gray-900 dark:text-gray-100">{{ file.name }}</td>
                            <td class="px-4 py-2 font-mono text-xs text-gray-500 dark:text-gray-400 break-all">{{ file.sha256 }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <!-- Flash via USB unavailable warning -->
                  <div
                    v-if="webSerialSupported && item.release_status !== 'DELETED' && !hasPartitionOffsets"
                    class="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
                  >
                    <strong>Flash via USB is unavailable.</strong>
                    Partition offset data is missing from this firmware record — the
                    <code class="font-mono">partitions.bin</code> file may be absent or corrupt.
                    Re-upload the firmware ZIP to generate a new record with partition data.
                  </div>

                </div>

                <!-- Footer -->
                <div class="border-t border-gray-200 dark:border-gray-700 px-6 py-4 flex items-center justify-between gap-4">
                  <!-- Left: Delete -->
                  <button
                    v-if="!NON_DELETABLE_STATES.has(item.release_status)"
                    @click="requestDelete"
                    class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
                  >
                    Delete
                  </button>
                  <div v-else />

                  <!-- Right: Flash + Download -->
                  <div class="flex items-center gap-2">
                    <!-- Flash via USB (Chrome / Web Serial only; not available for deleted firmware or missing partition data) -->
                    <button
                      v-if="webSerialSupported && item.release_status !== 'DELETED'"
                      @click="flashOpen = true"
                      :disabled="!hasPartitionOffsets"
                      class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                    >
                      <BoltIcon class="w-4 h-4" />
                      Flash via USB
                    </button>

                    <!-- Download ZIP -->
                    <button
                      v-if="item.release_status !== 'DELETED'"
                      @click="handleDownload"
                      :disabled="downloadLoading"
                      class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed rounded-lg transition-colors"
                    >
                      <template v-if="downloadLoading">
                        <svg class="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                        Getting URL…
                      </template>
                      <template v-else>
                        <ArrowDownTrayIcon class="w-4 h-4" />
                        Download ZIP
                      </template>
                    </button>
                  </div>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>

  <!-- Confirm modal -->
  <ConfirmModal
    :open="confirmOpen"
    :title="confirmTitle"
    :message="confirmMessage"
    :details="confirmDetails"
    :variant="confirmVariant"
    :confirm-label="confirmLabel"
    @confirm="handleConfirm"
    @cancel="handleCancel"
  />

  <!-- Flash modal -->
  <FirmwareFlashModal
    v-if="item && flashOpen"
    :open="flashOpen"
    :item="item"
    :zip-name="zipName"
    @close="flashOpen = false"
  />
</template>
