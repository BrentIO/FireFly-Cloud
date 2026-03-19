<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import {
  ArrowPathIcon,
  ChevronUpIcon,
  ChevronDownIcon,
} from '@heroicons/vue/24/outline'
import { useAuth } from '../composables/useAuth.js'
import { useToast } from '../composables/useToast.js'
import ConfirmModal from '../components/ConfirmModal.vue'
import AppLayout from '../components/AppLayout.vue'
import { listUsers, inviteUser, deleteUser, patchUser } from '../api/users.js'

const { isSuperUser } = useAuth()
const { showToast } = useToast()

const users   = ref([])
const loading = ref(true)

// ── Invite form ───────────────────────────────────────────────────────────────
const showInviteForm   = ref(false)
const inviteEmail      = ref('')
const inviteEnvs       = ref([])
const inviteSubmitting = ref(false)
const inviteError      = ref(null)

const EMAIL_RE = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/

// ── Confirm modal ─────────────────────────────────────────────────────────────
const confirmOpen    = ref(false)
const confirmTitle   = ref('')
const confirmMsg     = ref('')
const confirmVariant = ref('warning')
const confirmAction  = ref(null)

// ── Sort ──────────────────────────────────────────────────────────────────────
const sortKey = ref('email')
const sortDir = ref('asc')

// ── Pagination ────────────────────────────────────────────────────────────────
const currentPage = ref(1)
const pageSize    = ref(10)

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const data = await listUsers()
    users.value = data.users
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ── Sorting & pagination ──────────────────────────────────────────────────────
const sortedUsers = computed(() => {
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...users.value].sort((a, b) => {
    const av = (a[sortKey.value] ?? '').toString().toLowerCase()
    const bv = (b[sortKey.value] ?? '').toString().toLowerCase()
    if (av < bv) return -1 * dir
    if (av > bv) return 1 * dir
    return 0
  })
})

const totalItems = computed(() => sortedUsers.value.length)
const totalPages = computed(() => Math.max(1, Math.ceil(totalItems.value / pageSize.value)))

const paginatedUsers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return sortedUsers.value.slice(start, start + pageSize.value)
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

// ── Invite ────────────────────────────────────────────────────────────────────
function openInviteForm() {
  inviteEmail.value    = ''
  inviteEnvs.value     = []
  inviteError.value    = null
  showInviteForm.value = true
}

async function submitInvite() {
  inviteError.value = null

  const email = inviteEmail.value.trim().toLowerCase()
  if (!email) { inviteError.value = 'Email is required.'; return }
  if (!EMAIL_RE.test(email)) { inviteError.value = 'Enter a valid email address.'; return }
  if (inviteEnvs.value.length === 0) { inviteError.value = 'Select at least one environment.'; return }

  inviteSubmitting.value = true
  try {
    await inviteUser({ email, environments: inviteEnvs.value })
    showToast(`${email} has been added to the allowed list.`, 'success')
    showInviteForm.value = false
    await load()
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    inviteSubmitting.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────
function promptDelete(user) {
  confirmTitle.value   = 'Delete user'
  confirmMsg.value     = `Remove ${user.email} from FireFly? They will lose access immediately.`
  confirmVariant.value = 'danger'
  confirmAction.value  = () => doDelete(user.email)
  confirmOpen.value    = true
}

async function doDelete(email) {
  try {
    await deleteUser(email)
    showToast(`${email} has been deleted.`, 'success')
    await load()
  } catch (e) {
    showToast(e.message, 'error')
  }
}

// ── Super toggle ──────────────────────────────────────────────────────────────
function promptSuperToggle(user) {
  confirmTitle.value   = user.is_super ? 'Remove super user' : 'Grant super user'
  confirmMsg.value     = `${user.is_super ? 'Remove super status from' : 'Grant super status to'} ${user.email}?`
  confirmVariant.value = 'warning'
  confirmAction.value  = () => doSuperToggle(user)
  confirmOpen.value    = true
}

async function doSuperToggle(user) {
  try {
    await patchUser(user.email, { is_super: !user.is_super })
    showToast(
      user.is_super ? `${user.email} is no longer a super user.` : `${user.email} is now a super user.`,
      'success'
    )
    await load()
  } catch (e) {
    showToast(e.message, 'error')
  }
}

function onConfirm() {
  confirmOpen.value = false
  if (confirmAction.value) confirmAction.value()
}
</script>

<template>
  <AppLayout>
    <!-- Toolbar -->
    <div class="flex-shrink-0 flex items-center justify-between pb-4 flex-wrap gap-3">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Users</h1>

      <div class="flex items-center gap-3">
        <button
          v-if="isSuperUser"
          @click="openInviteForm"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
        >
          Invite User
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

    <!-- Invite form -->
    <div
      v-if="showInviteForm"
      class="flex-shrink-0 mb-4 bg-white dark:bg-gray-900 rounded-xl ring-1 ring-black/10 dark:ring-white/10 p-5 space-y-4"
    >
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Invite a new user</h3>

      <div class="space-y-1">
        <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">Email</label>
        <input
          v-model="inviteEmail"
          type="email"
          placeholder="user@example.com"
          class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div class="space-y-1">
        <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">Environments</label>
        <div class="flex gap-4">
          <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
            <input type="checkbox" value="dev"        v-model="inviteEnvs" class="rounded" /> dev
          </label>
          <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
            <input type="checkbox" value="production" v-model="inviteEnvs" class="rounded" /> production
          </label>
        </div>
      </div>

      <p v-if="inviteError" class="text-xs text-red-600 dark:text-red-400">{{ inviteError }}</p>

      <div class="flex gap-3">
        <button
          @click="submitInvite"
          :disabled="inviteSubmitting"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors"
        >
          {{ inviteSubmitting ? 'Adding…' : 'Add User' }}
        </button>
        <button
          @click="showInviteForm = false"
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
        >
          Cancel
        </button>
      </div>

      <p class="text-xs text-gray-500 dark:text-gray-400">
        After adding the user, tell them to sign in using the "Sign in with Google" button.
      </p>
    </div>

    <!-- Table card -->
    <div class="flex flex-col flex-1 min-h-0 bg-white dark:bg-gray-900 rounded-xl shadow-sm ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
      <div class="flex-1 overflow-x-auto overflow-y-auto min-h-0">
        <table class="w-full text-sm">
          <thead class="sticky top-0 z-10">
            <tr class="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('email')"
              >
                Email
                <ChevronUpIcon   v-if="sortKey === 'email' && sortDir === 'asc'"  class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'email' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th
                class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                @click="toggleSort('name')"
              >
                Name
                <ChevronUpIcon   v-if="sortKey === 'name' && sortDir === 'asc'"  class="inline w-3 h-3 ml-0.5" />
                <ChevronDownIcon v-else-if="sortKey === 'name' && sortDir === 'desc'" class="inline w-3 h-3 ml-0.5" />
              </th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap select-none">
                Environments
              </th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap select-none">
                Super User
              </th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>

          <tbody>
            <!-- Loading skeleton -->
            <template v-if="loading">
              <tr v-for="i in 8" :key="i" class="border-b border-gray-100 dark:border-gray-800">
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-40" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-28" /></td>
                <td class="px-4 py-3"><div class="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-16" /></td>
                <td class="px-4 py-3"><div class="h-5 bg-gray-200 dark:bg-gray-700 rounded-full animate-pulse w-12" /></td>
                <td class="px-4 py-3"></td>
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-else-if="paginatedUsers.length === 0">
              <td colspan="5" class="px-4 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                No users found.
              </td>
            </tr>

            <!-- Data rows -->
            <tr
              v-else
              v-for="user in paginatedUsers"
              :key="user.email"
              class="border-b border-gray-100 dark:border-gray-800 odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800/50 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
            >
              <td class="px-4 py-3 font-medium text-gray-900 dark:text-gray-100 whitespace-nowrap">{{ user.email }}</td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ user.name || '—' }}</td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span
                  v-for="env in (user.environments ? user.environments.split(',') : [])"
                  :key="env"
                  class="inline-block mr-1 px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                >{{ env.trim() }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span
                  v-if="user.is_super"
                  class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300"
                >
                  Super
                </span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <div class="flex items-center justify-end gap-2">
                  <button
                    @click="promptSuperToggle(user)"
                    class="px-3 py-1 text-xs font-medium rounded-lg border transition-colors text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-700 hover:bg-amber-50 dark:hover:bg-amber-900/30"
                  >
                    {{ user.is_super ? 'Revoke super' : 'Make super' }}
                  </button>
                  <button
                    @click="promptDelete(user)"
                    class="px-3 py-1 text-xs font-medium rounded-lg border transition-colors text-red-700 dark:text-red-400 border-red-300 dark:border-red-700 hover:bg-red-50 dark:hover:bg-red-900/30"
                  >
                    Delete
                  </button>
                </div>
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

    <!-- Confirm modal -->
    <ConfirmModal
      :open="confirmOpen"
      :title="confirmTitle"
      :message="confirmMsg"
      :variant="confirmVariant"
      confirmLabel="Confirm"
      @confirm="onConfirm"
      @cancel="confirmOpen = false"
    />
  </AppLayout>
</template>
