<script setup>
import { STATUS_LABELS, STATUS_STYLES, STATUS_DOT } from '../utils/formatters.js'

const props = defineProps({
  status: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium"
    :class="STATUS_STYLES[status] || 'bg-gray-100 text-gray-600'"
  >
    <span
      class="w-1.5 h-1.5 rounded-full"
      :class="STATUS_DOT[status] || 'bg-gray-400'"
    ></span>
    {{ STATUS_LABELS[status] || status }}
  </span>
</template>
