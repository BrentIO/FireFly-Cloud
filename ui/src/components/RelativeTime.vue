<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { formatRelativeDate, formatAbsoluteDate } from '../utils/formatters.js'

const props = defineProps({
  value: {
    type: [String, Number],
    required: true,
  },
})

const showAbsolute = ref(false)
const tick = ref(0)
let interval = null

onMounted(() => {
  interval = setInterval(() => {
    tick.value++
  }, 60000)
})

onUnmounted(() => {
  if (interval) clearInterval(interval)
})
</script>

<template>
  <span
    class="cursor-pointer hover:underline decoration-dotted text-sm text-gray-900 dark:text-gray-100"
    :title="showAbsolute ? undefined : formatAbsoluteDate(value)"
    @click="showAbsolute = !showAbsolute"
  >
    <template v-if="showAbsolute">{{ formatAbsoluteDate(value) }}</template>
    <template v-else>{{ formatRelativeDate(value) }}{{ tick >= 0 ? '' : '' }}</template>
  </span>
</template>
