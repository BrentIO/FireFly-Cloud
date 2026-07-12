<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue'

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
  confirmLabel: {
    type: String,
    default: 'Confirm',
  },
})

const emit = defineEmits(['confirm', 'cancel'])

// Deliberately not a HeadlessUI <Dialog>: this component is sometimes rendered
// nested inside another already-open <Dialog> (see FirmwareDetailModal). Two
// independent HeadlessUI Dialogs open at once conflict in their outside-press
// detection, which silently swallows taps on this modal's buttons on mobile
// Safari. A plain Teleport + Transition sidesteps that entirely.

const panelVisible = ref(false)
let scrollLockOwned = false

function lockScroll() {
  if (!scrollLockOwned) {
    scrollLockOwned = true
    document.body.style.overflow = 'hidden'
  }
}

function unlockScroll() {
  if (scrollLockOwned) {
    scrollLockOwned = false
    document.body.style.overflow = ''
  }
}

function onKeydown(event) {
  if (event.key === 'Escape') emit('cancel')
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      lockScroll()
      window.addEventListener('keydown', onKeydown)
      panelVisible.value = false
      await nextTick()
      requestAnimationFrame(() => {
        panelVisible.value = true
      })
    } else {
      unlockScroll()
      window.removeEventListener('keydown', onKeydown)
      panelVisible.value = false
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  unlockScroll()
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="ease-out duration-200 transition-opacity"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="ease-in duration-150 transition-opacity"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-50 overflow-y-auto"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        @click="emit('cancel')"
      >
        <div class="fixed inset-0 bg-black/50" />

        <div class="relative flex min-h-full items-center justify-center p-4">
          <div
            class="relative w-full max-w-md rounded-xl bg-white dark:bg-gray-900 shadow-xl ring-1 ring-black/10 dark:ring-white/10 p-6 transition-all duration-200 ease-out"
            :class="panelVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'"
            @click.stop
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
                class="px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors min-h-[44px]"
              >
                Cancel
              </button>
              <button
                type="button"
                @click="emit('confirm')"
                class="px-4 py-2.5 text-sm font-medium text-white rounded-lg transition-colors min-h-[44px]"
                :class="{
                  'bg-green-600 hover:bg-green-700': variant === 'success',
                  'bg-amber-500 hover:bg-amber-600': variant === 'warning',
                  'bg-red-600 hover:bg-red-700':     variant === 'danger' || !['success','warning'].includes(variant),
                }"
              >
                {{ confirmLabel }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
