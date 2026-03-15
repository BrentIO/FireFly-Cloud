<script setup>
import { useAuth } from '../composables/useAuth.js'

const { login } = useAuth()
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4">
    <div class="w-full max-w-sm">
      <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl ring-1 ring-black/10 dark:ring-white/10 p-8">
        <div class="text-center mb-8">
          <h1 class="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">FireFly</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400">Firmware Management Console</p>
        </div>

        <button
          @click="login()"
          class="w-full py-2.5 px-4 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
        >
          Login
        </button>
      </div>
    </div>
  </div>
</template>
