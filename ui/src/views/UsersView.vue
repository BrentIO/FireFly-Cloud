<script setup>
import { ref, onMounted } from 'vue'
import { useAuth } from '../composables/useAuth.js'
import { useToast } from '../composables/useToast.js'
import ConfirmModal from '../components/ConfirmModal.vue'
import AppLayout from '../components/AppLayout.vue'
import { listUsers, inviteUser, deleteUser, patchUser } from '../api/users.js'

const { isSuperUser } = useAuth()
const { showToast } = useToast()

const users   = ref([])
const loading = ref(true)
const error   = ref(null)

// Invite form
const showInviteForm  = ref(false)
const inviteEmail     = ref('')
const inviteEnvs      = ref([])
const inviteSubmitting = ref(false)
const inviteError     = ref(null)

const EMAIL_RE = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/

// Confirm modal
const confirmModal = ref(null)
const confirmOpen  = ref(false)
const confirmTitle = ref('')
const confirmMsg   = ref('')
const confirmVariant = ref('warning')
const confirmAction = ref(null)

async function load() {
  loading.value = true
  error.value   = null
  try {
    const data = await listUsers()
    users.value = data.users
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ---------------------------------------------------------------------------
// Invite
// ---------------------------------------------------------------------------

function openInviteForm() {
  inviteEmail.value    = ''
  inviteEnvs.value     = []
  inviteError.value    = null
  showInviteForm.value = true
}

async function submitInvite() {
  inviteError.value = null

  const email = inviteEmail.value.trim().toLowerCase()
  if (!email) {
    inviteError.value = 'Email is required.'
    return
  }
  if (!EMAIL_RE.test(email)) {
    inviteError.value = 'Enter a valid email address.'
    return
  }
  if (inviteEnvs.value.length === 0) {
    inviteError.value = 'Select at least one environment.'
    return
  }

  inviteSubmitting.value = true
  try {
    await inviteUser({ email, environments: inviteEnvs.value })
    showToast(`${email} has been added to the allowed list.`, 'success')
    showInviteForm.value = false
    await load()
  } catch (e) {
    inviteError.value = e.message
  } finally {
    inviteSubmitting.value = false
  }
}

// ---------------------------------------------------------------------------
// Delete user
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Toggle super user
// ---------------------------------------------------------------------------

function promptSuperToggle(user) {
  const action = user.is_super ? 'Remove super status from' : 'Grant super status to'
  confirmTitle.value   = user.is_super ? 'Remove super user' : 'Grant super user'
  confirmMsg.value     = `${action} ${user.email}?`
  confirmVariant.value = 'warning'
  confirmAction.value  = () => doSuperToggle(user)
  confirmOpen.value    = true
}

async function doSuperToggle(user) {
  try {
    await patchUser(user.email, { is_super: !user.is_super })
    showToast(
      user.is_super
        ? `${user.email} is no longer a super user.`
        : `${user.email} is now a super user.`,
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
  <AppLayout title="Users">
    <div class="max-w-4xl mx-auto px-4 py-6 space-y-6">

      <!-- Header -->
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">User Management</h2>
        <button
          v-if="isSuperUser"
          @click="openInviteForm"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
        >
          Invite User
        </button>
      </div>

      <!-- Invite form -->
      <div
        v-if="showInviteForm"
        class="bg-white dark:bg-gray-900 rounded-xl ring-1 ring-black/10 dark:ring-white/10 p-5 space-y-4"
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

      <!-- Loading / error -->
      <div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">Loading users…</div>
      <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</div>

      <!-- User table -->
      <div
        v-else-if="users.length"
        class="bg-white dark:bg-gray-900 rounded-xl ring-1 ring-black/10 dark:ring-white/10 overflow-hidden"
      >
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200 dark:border-gray-700 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              <th class="px-4 py-3">Email</th>
              <th class="px-4 py-3">Name</th>
              <th class="px-4 py-3">Environments</th>
              <th class="px-4 py-3">Super User</th>
              <th class="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
            <tr
              v-for="user in users"
              :key="user.email"
              class="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
            >
              <td class="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{{ user.email }}</td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400">{{ user.name || '—' }}</td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400">
                <span
                  v-for="env in (user.environments ? user.environments.split(',') : [])"
                  :key="env"
                  class="inline-block mr-1 px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                >{{ env.trim() }}</span>
              </td>
              <td class="px-4 py-3">
                <span
                  v-if="user.is_super"
                  class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300"
                >
                  Super
                </span>
              </td>
              <td class="px-4 py-3 text-right">
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

      <p v-else class="text-sm text-gray-500 dark:text-gray-400">No users found.</p>
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
