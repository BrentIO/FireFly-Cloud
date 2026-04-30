<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { SunIcon, MoonIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { useAuth } from '../composables/useAuth.js'
import { useTheme } from '../composables/useTheme.js'

defineEmits(['close'])

const route = useRoute()
const { isSuperUser, userName, userEmail, logout } = useAuth()
const { isDark, toggleTheme } = useTheme()

const refName   = import.meta.env.VITE_REF_NAME   || null
const commitSha = import.meta.env.VITE_COMMIT_SHA  || null

const uiVersion = computed(() => {
  if (refName && commitSha) return `${refName} (${commitSha.slice(0, 7)})`
  if (refName)   return refName
  if (commitSha) return commitSha.slice(0, 7)
  return 'dev'
})
</script>

<template>
  <nav class="w-64 bg-gray-900 dark:bg-gray-950 text-white flex flex-col flex-shrink-0 h-screen border-r border-gray-700 dark:border-gray-800">
    <!-- Header -->
    <div class="px-4 py-4 flex items-start justify-between gap-2 border-b border-gray-700 dark:border-gray-800">
      <span class="text-sm font-semibold text-gray-100 leading-snug">FireFly Management Console</span>
      <div class="flex items-center gap-1 flex-shrink-0 mt-0.5">
        <!-- Close button — mobile only -->
        <button
          class="p-1 rounded text-gray-400 hover:text-gray-100 hover:bg-gray-800 transition-colors md:hidden"
          aria-label="Close menu"
          @click="$emit('close')"
        >
          <XMarkIcon class="w-4 h-4" />
        </button>
        <!-- Theme toggle -->
        <button
          class="p-1 rounded text-gray-400 hover:text-gray-100 hover:bg-gray-800 transition-colors"
          :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
          @click="toggleTheme()"
        >
          <SunIcon v-if="isDark" class="w-4 h-4" />
          <MoonIcon v-else class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Nav links -->
    <ul class="flex-1 py-2 overflow-y-auto">
      <li>
        <RouterLink
          to="/firmware"
          class="flex items-center px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-gray-100 transition-colors rounded-sm mx-1"
          :class="{ 'bg-gray-800 text-gray-100': route.path.startsWith('/firmware') }"
          @click="$emit('close')"
        >
          Firmware
        </RouterLink>
      </li>
      <li v-if="isSuperUser">
        <RouterLink
          to="/devices"
          class="flex items-center px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-gray-100 transition-colors rounded-sm mx-1"
          :class="{ 'bg-gray-800 text-gray-100': route.path.startsWith('/devices') }"
          @click="$emit('close')"
        >
          Registered Devices
        </RouterLink>
      </li>
      <li v-if="isSuperUser">
        <RouterLink
          to="/users"
          class="flex items-center px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-gray-100 transition-colors rounded-sm mx-1"
          :class="{ 'bg-gray-800 text-gray-100': route.path.startsWith('/users') }"
          @click="$emit('close')"
        >
          Users
        </RouterLink>
      </li>
      <li v-if="isSuperUser">
        <RouterLink
          to="/appconfig"
          class="flex items-center px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-gray-100 transition-colors rounded-sm mx-1"
          :class="{ 'bg-gray-800 text-gray-100': route.path.startsWith('/appconfig') }"
          @click="$emit('close')"
        >
          App Configuration
        </RouterLink>
      </li>
    </ul>

    <!-- Footer -->
    <div class="px-4 py-3 border-t border-gray-700 dark:border-gray-800 space-y-2">
      <div class="text-[10px] font-mono text-gray-600 select-all">UI: {{ uiVersion }}</div>
      <div v-if="userName || userEmail" class="space-y-0.5">
        <div v-if="userName" class="text-xs font-medium text-gray-400 truncate">{{ userName }}</div>
        <div v-if="userEmail" class="text-[10px] text-gray-600 truncate">{{ userEmail }}</div>
      </div>
      <button
        @click="logout()"
        class="w-full text-left text-sm text-gray-400 hover:text-gray-100 px-1 py-1 rounded hover:bg-gray-800 transition-colors"
      >
        Logout
      </button>
    </div>
  </nav>
</template>
