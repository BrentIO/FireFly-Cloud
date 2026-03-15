import { ref, computed } from 'vue'

const THEME_KEY = 'firefly_theme'
const theme = ref(localStorage.getItem(THEME_KEY) || 'system')

const isDark = computed(() => {
  if (theme.value === 'dark') return true
  if (theme.value === 'light') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
})

function applyTheme() {
  document.documentElement.classList.toggle('dark', isDark.value)
}

function setTheme(value) {
  theme.value = value
  localStorage.setItem(THEME_KEY, value)
  applyTheme()
}

function toggleTheme() {
  setTheme(isDark.value ? 'light' : 'dark')
}

export function useTheme() {
  return { theme, applyTheme, setTheme, toggleTheme, isDark }
}
