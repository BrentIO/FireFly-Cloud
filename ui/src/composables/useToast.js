import { ref } from 'vue'

const toasts = ref([])
let nextId = 1

function success(message) {
  const id = nextId++
  toasts.value.push({ id, type: 'success', message, detail: null })
  setTimeout(() => removeToast(id), 5000)
}

function error(message, detail = null) {
  if (detail) {
    console.error(detail)
  }
  const id = nextId++
  toasts.value.push({ id, type: 'error', message, detail })
}

function removeToast(id) {
  const index = toasts.value.findIndex((t) => t.id === id)
  if (index !== -1) {
    toasts.value.splice(index, 1)
  }
}

export function useToast() {
  return { toasts, success, error, removeToast }
}
