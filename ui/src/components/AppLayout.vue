<script setup>
import { ref } from 'vue'
import { Bars3Icon, SunIcon, MoonIcon } from '@heroicons/vue/24/outline'
import NavDrawer from './NavDrawer.vue'
import { useTheme } from '../composables/useTheme.js'

const navOpen = ref(false)
const { toggleTheme, isDark } = useTheme()
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50 dark:bg-gray-950">
    <!-- Header -->
    <header class="flex-shrink-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-4 h-14 flex items-center">
      <div class="flex items-center justify-between w-full">
        <!-- Hamburger -->
        <button
          @click="navOpen = true"
          class="rounded-md p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Open navigation"
        >
          <Bars3Icon class="w-5 h-5" />
        </button>

        <!-- Title -->
        <span class="text-base font-semibold text-gray-900 dark:text-gray-100 absolute left-1/2 -translate-x-1/2">
          FireFly Management Console
        </span>

        <!-- Theme toggle -->
        <button
          @click="toggleTheme()"
          class="rounded-md p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Toggle theme"
        >
          <MoonIcon v-if="!isDark" class="w-5 h-5" />
          <SunIcon v-else class="w-5 h-5" />
        </button>
      </div>
    </header>

    <!-- Nav Drawer -->
    <NavDrawer :open="navOpen" @close="navOpen = false" />

    <!-- Page content -->
    <main class="flex-1 overflow-hidden flex flex-col p-4 sm:p-6">
      <slot />
    </main>
  </div>
</template>
