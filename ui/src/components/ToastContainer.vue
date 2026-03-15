<script setup>
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { useToast } from '../composables/useToast.js'

const { toasts, removeToast } = useToast()
</script>

<template>
  <div class="fixed top-4 right-4 z-50 flex flex-col gap-2 w-80">
    <TransitionGroup name="toast" tag="div" class="flex flex-col gap-2">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="rounded-lg px-4 py-3 shadow-lg flex items-start gap-3"
        :class="
          toast.type === 'success'
            ? 'bg-green-50 border border-green-200 dark:bg-green-900/50 dark:border-green-700 text-green-800 dark:text-green-200'
            : 'bg-red-50 border border-red-200 dark:bg-red-900/50 dark:border-red-700 text-red-800 dark:text-red-200'
        "
      >
        <p class="flex-1 text-sm font-medium">{{ toast.message }}</p>
        <button
          @click="removeToast(toast.id)"
          class="flex-shrink-0 ml-1 rounded hover:opacity-70 transition-opacity"
          aria-label="Dismiss"
        >
          <XMarkIcon class="w-4 h-4" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
