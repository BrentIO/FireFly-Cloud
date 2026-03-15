<script setup>
import {
  Dialog,
  DialogPanel,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'

const props = defineProps({
  open: {
    type: Boolean,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  message: {
    type: String,
    required: true,
  },
  details: {
    type: Object,
    default: null,
  },
  variant: {
    type: String,
    default: 'danger',
  },
})

const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-50" @close="emit('cancel')">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-150"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/50 transition-opacity" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-200"
            enter-from="opacity-0 scale-95"
            enter-to="opacity-100 scale-100"
            leave="ease-in duration-150"
            leave-from="opacity-100 scale-100"
            leave-to="opacity-0 scale-95"
          >
            <DialogPanel
              class="relative w-full max-w-md rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 p-6"
            >
              <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
                {{ title }}
              </h3>
              <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">{{ message }}</p>

              <div
                v-if="details && Object.keys(details).length"
                class="mb-4 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700"
              >
                <div
                  v-for="(val, key) in details"
                  :key="key"
                  class="px-3 py-2"
                >
                  <p class="text-xs text-gray-500 dark:text-gray-400 mb-0.5">{{ key }}</p>
                  <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ val }}</p>
                </div>
              </div>

              <div class="flex gap-3 justify-end">
                <button
                  type="button"
                  @click="emit('cancel')"
                  class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  @click="emit('confirm')"
                  class="px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors"
                  :class="variant === 'success' ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'"
                >
                  Confirm
                </button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
