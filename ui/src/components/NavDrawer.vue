<script setup>
import {
  Dialog,
  DialogPanel,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { useRoute } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'

const props = defineProps({
  open: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['close'])
const route = useRoute()
const { logout, isSuperUser, userName, userEmail } = useAuth()
const commitSha = import.meta.env.VITE_COMMIT_SHA || null
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-40" @close="emit('close')">
      <TransitionChild
        as="template"
        enter="ease-in-out duration-300"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in-out duration-300"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/50 transition-opacity" />
      </TransitionChild>

      <div class="fixed inset-0 flex">
        <TransitionChild
          as="template"
          enter="ease-in-out duration-300"
          enter-from="-translate-x-full"
          enter-to="translate-x-0"
          leave="ease-in-out duration-300"
          leave-from="translate-x-0"
          leave-to="-translate-x-full"
        >
          <DialogPanel
            class="relative flex w-64 flex-col bg-white dark:bg-gray-900 h-full shadow-xl"
          >
            <!-- Header -->
            <div class="flex items-center justify-between px-4 h-14 border-b border-gray-200 dark:border-gray-700">
              <div v-if="userName || userEmail" class="flex flex-col min-w-0">
                <span v-if="userName" class="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">{{ userName }}</span>
                <span v-if="userEmail" class="text-[10px] text-gray-400 dark:text-gray-500 truncate">{{ userEmail }}</span>
              </div>
              <div v-else />
              <button
                @click="emit('close')"
                class="rounded-md p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label="Close navigation"
              >
                <XMarkIcon class="w-5 h-5" />
              </button>
            </div>

            <!-- Nav links -->
            <nav class="px-3 py-4 space-y-1">
              <RouterLink
                to="/firmware"
                @click="emit('close')"
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
                :class="
                  route.path.startsWith('/firmware')
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                "
              >
                Firmware
              </RouterLink>

              <RouterLink
                v-if="isSuperUser"
                to="/users"
                @click="emit('close')"
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
                :class="
                  route.path.startsWith('/users')
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                "
              >
                Users
              </RouterLink>

              <RouterLink
                v-if="isSuperUser"
                to="/appconfig"
                @click="emit('close')"
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
                :class="
                  route.path.startsWith('/appconfig')
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                "
              >
                AppConfig
              </RouterLink>
            </nav>

            <!-- Spacer -->
            <div class="flex-1" />

            <!-- Commit SHA -->
            <p v-if="commitSha" class="px-6 pb-2 text-[10px] font-mono text-gray-400 dark:text-gray-600 select-all">
              Commit: {{ commitSha.slice(0, 8) }}
            </p>

            <!-- Logout -->
            <div class="px-3 py-4 border-t border-gray-200 dark:border-gray-700">
              <button
                @click="logout()"
                class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                Logout
              </button>
            </div>
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
