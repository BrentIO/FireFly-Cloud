<script setup>
import { onMounted } from 'vue'
import { useTheme } from './composables/useTheme.js'
import ToastContainer from './components/ToastContainer.vue'
const { applyTheme } = useTheme()
onMounted(applyTheme)
</script>
<template>
  <div>
    <RouterView />
    <ToastContainer />
  </div>
</template>
