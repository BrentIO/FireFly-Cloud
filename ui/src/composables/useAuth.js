import router from '../router/index.js'

const AUTH_KEY = 'firefly_authenticated'

export function useAuth() {
  function login() {
    sessionStorage.setItem(AUTH_KEY, 'true')
    router.push('/firmware')
  }

  function logout() {
    sessionStorage.removeItem(AUTH_KEY)
    router.push('/login')
  }

  function isAuthenticated() {
    return !!sessionStorage.getItem(AUTH_KEY)
  }

  return { login, logout, isAuthenticated }
}
