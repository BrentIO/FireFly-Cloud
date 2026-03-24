<script setup>
import { ref, onMounted } from 'vue'
import {
  ArrowPathIcon,
  PencilSquareIcon,
  XMarkIcon,
  PlusIcon,
} from '@heroicons/vue/24/outline'
import {
  Dialog,
  DialogPanel,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
import AppLayout from '../components/AppLayout.vue'
import { useToast } from '../composables/useToast.js'
import { listAppConfig, patchAppConfig } from '../api/appconfig.js'

const { success: successToast, error: errorToast } = useToast()

const applications = ref([])
const loading      = ref(true)

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const data = await listAppConfig()
    applications.value = data.applications
  } catch (e) {
    errorToast(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ── Edit modal ────────────────────────────────────────────────────────────────
const showEditModal    = ref(false)
const editApp          = ref(null)
const editRules        = ref([])
const editSubmitting   = ref(false)
const editError        = ref(null)

function openEditModal(app) {
  editApp.value        = app
  editError.value      = null
  editSubmitting.value = false
  // Clone the logging rules into editable objects { prefix, level }
  editRules.value = (app.logging ?? []).map(entry => {
    const [prefix, level] = Object.entries(entry)[0]
    return { prefix, level }
  })
  showEditModal.value = true
}

function addRule() {
  editRules.value.push({ prefix: '', level: 'INFO' })
}

function removeRule(index) {
  editRules.value.splice(index, 1)
}

async function submitEdit() {
  editError.value = null

  for (let i = 0; i < editRules.value.length; i++) {
    const rule = editRules.value[i]
    if (!rule.prefix.trim()) {
      editError.value = `Rule ${i + 1}: prefix is required.`
      return
    }
    if (!LOG_LEVELS.includes(rule.level)) {
      editError.value = `Rule ${i + 1}: invalid log level.`
      return
    }
  }

  const logging = editRules.value.map(r => ({ [r.prefix.trim()]: r.level }))

  editSubmitting.value = true
  try {
    await patchAppConfig(editApp.value.name, logging)
    showEditModal.value = false
    successToast(`Logging config updated for ${editApp.value.name}.`)
    await load()
  } catch (e) {
    editError.value = e.message
  } finally {
    editSubmitting.value = false
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
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">
                Application
              </th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none whitespace-nowrap">
                Logging Rules
              </th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>

          <tbody>
            <!-- Loading skeleton -->
            <template v-if="loading">
              <tr v-for="i in 6" :key="i" class="border-b border-gray-100 dark:border-gray-800">
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-64" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-48" /></td>
                <td class="px-4 py-3"></td>
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-else-if="applications.length === 0">
              <td colspan="3" class="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                No applications found.
              </td>
            </tr>

            <!-- Data rows -->
            <tr
              v-else
              v-for="app in applications"
              :key="app.id"
              class="border-b border-gray-100 dark:border-gray-800 odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800/50 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
            >
              <td class="px-4 py-3 font-mono text-xs text-gray-900 dark:text-gray-100 whitespace-nowrap align-top pt-4">
                {{ app.name }}
              </td>
              <td class="px-4 py-3 align-top pt-3">
                <div v-if="!app.logging || app.logging.length === 0" class="text-xs text-gray-400 dark:text-gray-500">
                  No rules
                </div>
                <div v-else class="flex flex-wrap gap-1.5">
                  <span
                    v-for="(entry, i) in app.logging"
                    :key="i"
                    class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-mono"
                  >
                    <span>{{ Object.keys(entry)[0] }}</span>
                    <span class="font-semibold" :class="{
                      'text-red-600 dark:text-red-400':    Object.values(entry)[0] === 'ERROR' || Object.values(entry)[0] === 'CRITICAL',
                      'text-amber-600 dark:text-amber-400': Object.values(entry)[0] === 'WARNING',
                      'text-blue-600 dark:text-blue-400':  Object.values(entry)[0] === 'DEBUG',
                      'text-gray-600 dark:text-gray-400':  Object.values(entry)[0] === 'INFO',
                    }">{{ Object.values(entry)[0] }}</span>
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-right align-top pt-3 whitespace-nowrap">
                <button
                  @click="openEditModal(app)"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  <PencilSquareIcon class="w-3.5 h-3.5" />
                  Configure
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Edit modal -->
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
                class="relative w-full max-w-lg rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 p-6 space-y-4"
                @click.stop
              >
                <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">Edit Logging Config</h3>
                <p class="text-xs font-mono text-gray-500 dark:text-gray-400 break-all">{{ editApp?.name }}</p>

                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <label class="text-xs font-medium text-gray-700 dark:text-gray-300">Rules</label>
                    <button
                      @click="addRule"
                      class="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
                    >
                      <PlusIcon class="w-3.5 h-3.5" />
                      Add rule
                    </button>
                  </div>

                  <div v-if="editRules.length === 0" class="text-xs text-gray-400 dark:text-gray-500 py-2">
                    No rules. Add a rule to control log levels for this application.
                  </div>

                  <div
                    v-for="(rule, i) in editRules"
                    :key="i"
                    class="flex items-center gap-2"
                  >
                    <input
                      v-model="rule.prefix"
                      type="text"
                      placeholder="function-name-prefix"
                      class="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs font-mono text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <select
                      v-model="rule.level"
                      class="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option v-for="lvl in LOG_LEVELS" :key="lvl" :value="lvl">{{ lvl }}</option>
                    </select>
                    <button
                      @click="removeRule(i)"
                      class="rounded p-1 text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                      aria-label="Remove rule"
                    >
                      <XMarkIcon class="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <p class="text-xs text-gray-500 dark:text-gray-400">
                  Each rule maps a function name prefix to a log level. When a function name
                  matches multiple prefixes, the most verbose level is used.
                </p>

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
