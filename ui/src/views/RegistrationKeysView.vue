<script setup>
import { ref, onMounted } from 'vue'
import {
  ArrowPathIcon,
  ClipboardDocumentIcon,
  ClipboardDocumentCheckIcon,
} from '@heroicons/vue/24/outline'
import { useToast } from '../composables/useToast.js'
import AppLayout from '../components/AppLayout.vue'
import { listRegistrationKeys, createRegistrationKey } from '../api/registration-keys.js'

const { success: successToast, error: errorToast } = useToast()

const keys      = ref([])
const loading   = ref(true)
const generating = ref(false)
const newKey    = ref(null)
const copiedKey = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await listRegistrationKeys()
    keys.value = data.registration_keys
  } catch (e) {
    errorToast(e.message)
  } finally {
    loading.value = false
  }
}

async function generate() {
  generating.value = true
  newKey.value = null
  try {
    const data = await createRegistrationKey()
    newKey.value = data.key
    successToast('Registration key generated.')
    await load()
  } catch (e) {
    errorToast(e.message)
  } finally {
    generating.value = false
  }
}

async function copyToClipboard(key) {
  try {
    await navigator.clipboard.writeText(key)
    copiedKey.value = key
    setTimeout(() => { if (copiedKey.value === key) copiedKey.value = null }, 2000)
  } catch {
    errorToast('Could not copy to clipboard.')
  }
}

function formatExpiry(unixSeconds) {
  if (!unixSeconds) return '—'
  return new Date(unixSeconds * 1000).toLocaleString()
}

function minutesRemaining(unixSeconds) {
  const diff = unixSeconds - Math.floor(Date.now() / 1000)
  if (diff <= 0) return 'Expired'
  const m = Math.ceil(diff / 60)
  return `${m} min`
}

onMounted(load)
</script>

<template>
  <AppLayout>
    <!-- Toolbar -->
    <div class="flex-shrink-0 flex items-center justify-between pb-4 flex-wrap gap-3">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Registration Keys</h1>

      <div class="flex items-center gap-3">
        <button
          @click="generate"
          :disabled="generating"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors"
        >
          <ArrowPathIcon v-if="generating" class="inline w-4 h-4 mr-1.5 animate-spin" />
          Generate New Key
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

    <!-- Newly generated key banner -->
    <Transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="newKey"
        class="flex-shrink-0 mb-4 rounded-xl bg-green-50 dark:bg-green-900/20 ring-1 ring-green-200 dark:ring-green-700 px-6 py-4"
      >
        <p class="text-xs font-semibold uppercase tracking-wide text-green-700 dark:text-green-400 mb-3">New Key Generated</p>
        <div class="flex items-center gap-4">
          <span class="text-4xl font-mono font-bold tracking-widest text-gray-900 dark:text-gray-100 select-all">
            {{ newKey }}
          </span>
          <button
            @click="copyToClipboard(newKey)"
            class="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-green-100 dark:hover:bg-green-800 transition-colors"
            :aria-label="copiedKey === newKey ? 'Copied' : 'Copy to clipboard'"
          >
            <ClipboardDocumentCheckIcon v-if="copiedKey === newKey" class="w-6 h-6 text-green-600 dark:text-green-400" />
            <ClipboardDocumentIcon v-else class="w-6 h-6" />
          </button>
        </div>
        <p class="mt-3 text-xs text-green-700 dark:text-green-400">
          This key expires in 30 minutes. Enter it in the HW-Reg Cloud Registration screen on the device being registered. Each key can only be used once.
        </p>
      </div>
    </Transition>

    <!-- Table card -->
    <div class="flex flex-col flex-1 min-h-0 bg-white dark:bg-gray-900 rounded-xl shadow-sm ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
      <div class="flex-1 overflow-x-auto overflow-y-auto min-h-0">
        <table class="w-full text-sm">
          <thead class="sticky top-0 z-10">
            <tr class="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap">Key</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap">Generated</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap">Expires</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap">Time Remaining</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>

          <tbody>
            <!-- Loading skeleton -->
            <template v-if="loading">
              <tr v-for="i in 3" :key="i" class="border-b border-gray-100 dark:border-gray-800">
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-16" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-36" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-36" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-16" /></td>
                <td class="px-4 py-3"></td>
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-else-if="keys.length === 0">
              <td colspan="5" class="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                No active registration keys. Generate one above.
              </td>
            </tr>

            <!-- Data rows -->
            <tr
              v-else
              v-for="k in keys"
              :key="k.key"
              class="border-b border-gray-100 dark:border-gray-800 odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800/50"
            >
              <td class="px-4 py-3 font-mono text-lg font-bold tracking-widest text-gray-900 dark:text-gray-100 select-all">{{ k.key }}</td>
              <td class="px-4 py-3 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{{ formatExpiry(k.generated_at) }}</td>
              <td class="px-4 py-3 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{{ formatExpiry(k.expires_at) }}</td>
              <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ minutesRemaining(k.expires_at) }}</td>
              <td class="px-4 py-3 text-right">
                <button
                  @click="copyToClipboard(k.key)"
                  class="p-1.5 rounded text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  :aria-label="copiedKey === k.key ? 'Copied' : 'Copy key'"
                >
                  <ClipboardDocumentCheckIcon v-if="copiedKey === k.key" class="w-4 h-4 text-green-500" />
                  <ClipboardDocumentIcon v-else class="w-4 h-4" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </AppLayout>
</template>
