<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'

const router = useRouter()
const { handleCallback } = useAuth()
const error = ref(null)

onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  const code   = params.get('code')
  const errParam = params.get('error')

  if (errParam) {
    const desc = params.get('error_description') || errParam
    error.value = desc.replace(/^PreSignUp failed with error\s+/, '').replace(/\.{2,}$/, '.')
    return
  }

  if (!code) {
    error.value = 'No authorization code received.'
    return
  }

  try {
    await handleCallback(code)
  } catch (e) {
    error.value = e.message || 'Authentication failed.'
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4">
    <div class="w-full max-w-sm text-center">
      <div v-if="error" class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl ring-1 ring-black/10 dark:ring-white/10 p-8">
        <p class="text-sm text-red-600 dark:text-red-400 mb-4">{{ error }}</p>
        <a href="/login" class="text-sm text-blue-600 dark:text-blue-400 hover:underline">Return to login</a>
      </div>
      <div v-else class="text-sm text-gray-500 dark:text-gray-400">
        Signing in&hellip;
      </div>
    </div>
  </div>
</template>
