<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  ArrowPathIcon,
  PencilSquareIcon,
  RocketLaunchIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import {
  Dialog,
  DialogPanel,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
import AppLayout from '../components/AppLayout.vue'
import { useToast } from '../composables/useToast.js'
import { getAppConfig, patchAppConfig, deployAppConfig } from '../api/appconfig.js'

const { success: successToast, error: errorToast } = useToast()

const applications = ref([])
const loading      = ref(true)

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

const LEVEL_CLASS = {
  DEBUG:    'text-blue-600 dark:text-blue-400',
  INFO:     'text-gray-600 dark:text-gray-400',
  WARNING:  'text-amber-600 dark:text-amber-400',
  ERROR:    'text-red-600 dark:text-red-400',
  CRITICAL: 'text-red-700 dark:text-red-500',
}

// Strip the "firefly-" prefix for display
function shortName(name) {
  return name.startsWith('firefly-') ? name.slice('firefly-'.length) : name
}

function hasPendingDeploy(app) {
  if (app.version === null) return false
  return app.deployed_version === null || app.deployed_version < app.version
}

function isDeploying(app) {
  return app.status && app.status !== 'COMPLETE' && app.status !== 'ROLLED_BACK'
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const data = await getAppConfig()
    applications.value = data.applications ?? []
  } catch (e) {
    errorToast(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ── Edit modal ────────────────────────────────────────────────────────────────
const showEditModal  = ref(false)
const editTarget     = ref(null)   // the application object being edited
const editLevel      = ref('WARNING')
const editSubmitting = ref(false)
const editError      = ref(null)

function openEditModal(app) {
  editTarget.value     = app
  editLevel.value      = app.logging ?? 'WARNING'
  editError.value      = null
  editSubmitting.value = false
  showEditModal.value  = true
}

async function submitEdit() {
  editError.value = null
  editSubmitting.value = true
  try {
    await patchAppConfig(editTarget.value.name, { logging: editLevel.value })
    showEditModal.value = false
    successToast(`Staged ${editLevel.value} for ${shortName(editTarget.value.name)}.`)
    await load()
  } catch (e) {
    editError.value = e.message
  } finally {
    editSubmitting.value = false
  }
}

// ── Deploy ────────────────────────────────────────────────────────────────────
const deploying = ref({})   // { functionName: true } while deploy is in flight

async function deploy(app) {
  deploying.value = { ...deploying.value, [app.name]: true }
  try {
    await deployAppConfig(app.name)
    successToast(`Deploying ${shortName(app.name)}…`)
    await load()
  } catch (e) {
    errorToast(e.message)
  } finally {
    const next = { ...deploying.value }
    delete next[app.name]
    deploying.value = next
  }
}
</script>

<template>
  <AppLayout>
    <!-- Toolbar -->
    <div class="flex-shrink-0 flex items-center justify-between pb-4 flex-wrap gap-3">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Configuration</h1>
      <button
        @click="load"
        :disabled="loading"
        class="rounded-md p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
        aria-label="Refresh"
      >
        <ArrowPathIcon class="w-5 h-5" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <!-- Table card -->
    <div class="flex flex-col flex-1 min-h-0 bg-white dark:bg-gray-900 rounded-xl shadow-sm ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
      <div class="flex-1 overflow-x-auto overflow-y-auto min-h-0">
        <table class="w-full text-sm">
          <thead class="sticky top-0 z-10">
            <tr class="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">Function</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">Log Level</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">Version</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">Status</th>
              <th class="px-4 py-3" />
            </tr>
          </thead>

          <tbody>
            <!-- Loading skeleton -->
            <template v-if="loading">
              <tr v-for="i in 6" :key="i" class="border-b border-gray-100 dark:border-gray-800">
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-56" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-20" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-16" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-24" /></td>
                <td class="px-4 py-3" />
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-else-if="applications.length === 0">
              <td colspan="5" class="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                No Lambda functions found.
              </td>
            </tr>

            <!-- Data rows -->
            <tr
              v-else
              v-for="app in applications"
              :key="app.name"
              class="border-b border-gray-100 dark:border-gray-800 odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800/50"
            >
              <!-- Function name -->
              <td class="px-4 py-3 font-mono text-xs text-gray-900 dark:text-gray-100 whitespace-nowrap">
                {{ shortName(app.name) }}
              </td>

              <!-- Log level -->
              <td class="px-4 py-3 font-mono text-xs font-semibold whitespace-nowrap"
                  :class="app.logging ? LEVEL_CLASS[app.logging] : 'text-gray-400 dark:text-gray-600'">
                {{ app.logging ?? 'default (WARNING)' }}
              </td>

              <!-- Version -->
              <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                <template v-if="app.version !== null">
                  <span>v{{ app.version }}</span>
                  <span v-if="hasPendingDeploy(app)"
                        class="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
                    staged
                  </span>
                </template>
                <span v-else class="text-gray-400 dark:text-gray-600">—</span>
              </td>

              <!-- Deployment status -->
              <td class="px-4 py-3 text-xs whitespace-nowrap">
                <template v-if="isDeploying(app)">
                  <span class="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400">
                    <svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                    </svg>
                    {{ app.status }}
                  </span>
                </template>
                <template v-else-if="app.status === 'COMPLETE'">
                  <span class="text-green-600 dark:text-green-400">✓ v{{ app.deployed_version }} deployed</span>
                </template>
                <template v-else-if="app.status === 'ROLLED_BACK'">
                  <span class="text-red-600 dark:text-red-400">✗ rolled back</span>
                </template>
                <span v-else class="text-gray-400 dark:text-gray-600">not deployed</span>
              </td>

              <!-- Actions -->
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="flex items-center justify-end gap-2">
                  <button
                    @click="openEditModal(app)"
                    class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    :title="`Configure ${app.name}`"
                  >
                    <PencilSquareIcon class="w-3.5 h-3.5" />
                    Configure
                  </button>
                  <button
                    @click="deploy(app)"
                    :disabled="!hasPendingDeploy(app) || isDeploying(app) || deploying[app.name]"
                    class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    :class="hasPendingDeploy(app) && !isDeploying(app)
                      ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-white dark:bg-gray-800 hover:bg-blue-50 dark:hover:bg-blue-900/20'
                      : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-500 bg-white dark:bg-gray-800'"
                    :title="hasPendingDeploy(app) ? `Deploy v${app.version} to ${app.name}` : 'No staged changes'"
                  >
                    <RocketLaunchIcon class="w-3.5 h-3.5" />
                    Deploy
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Configure modal -->
    <TransitionRoot :show="showEditModal" as="template">
      <Dialog as="div" class="relative z-50" @close="showEditModal = false">
        <TransitionChild
          as="template"
          enter="ease-out duration-200" enter-from="opacity-0" enter-to="opacity-100"
          leave="ease-in duration-150" leave-from="opacity-100" leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50 transition-opacity" />
        </TransitionChild>

        <div class="fixed inset-0 z-10 overflow-y-auto" @click="showEditModal = false">
          <div class="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as="template"
              enter="ease-out duration-200" enter-from="opacity-0 scale-95" enter-to="opacity-100 scale-100"
              leave="ease-in duration-150" leave-from="opacity-100 scale-100" leave-to="opacity-0 scale-95"
            >
              <DialogPanel
                class="relative w-full max-w-sm rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 p-6 space-y-4"
                @click.stop
              >
                <div class="flex items-start justify-between">
                  <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">Configure Function</h3>
                    <p class="mt-0.5 text-xs font-mono text-gray-500 dark:text-gray-400">{{ editTarget?.name }}</p>
                  </div>
                  <button @click="showEditModal = false" class="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                    <XMarkIcon class="w-4 h-4" />
                  </button>
                </div>

                <div class="space-y-1">
                  <label class="text-xs font-medium text-gray-700 dark:text-gray-300">Log Level</label>
                  <select
                    v-model="editLevel"
                    class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option v-for="lvl in LOG_LEVELS" :key="lvl" :value="lvl">{{ lvl }}</option>
                  </select>
                  <p class="text-xs text-gray-500 dark:text-gray-400 pt-1">
                    Changes are staged and must be deployed to take effect.
                  </p>
                </div>

                <p v-if="editError" class="text-xs text-red-600 dark:text-red-400">{{ editError }}</p>

                <div class="flex gap-3 justify-end">
                  <button
                    @click="showEditModal = false"
                    class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    @click="submitEdit"
                    :disabled="editSubmitting"
                    class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors"
                  >
                    {{ editSubmitting ? 'Saving…' : 'Save' }}
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
