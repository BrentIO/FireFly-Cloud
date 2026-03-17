/**
 * Cognito PKCE authentication composable.
 *
 * Token storage strategy:
 *   - access_token + id_token: reactive in-memory only (cleared on page reload)
 *   - refresh_token: sessionStorage (survives same-tab navigation, cleared on tab close)
 *
 * Session behaviour:
 *   - Each route navigation attempts a token refresh if the access token is
 *     absent or expired. Active users stay logged in indefinitely.
 *   - After the refresh token expires (Cognito default: 30 days), the next
 *     navigation returns a 401 and the user is redirected to /login.
 *   - Amplify auto-refresh is NOT used; all refresh logic is explicit and
 *     triggered only by navigation.
 */

import { ref, computed } from 'vue'
import router from '../router/index.js'

const COGNITO_DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN   // e.g. https://firefly-xxx.auth.us-east-1.amazoncognito.com
const CLIENT_ID      = import.meta.env.VITE_COGNITO_CLIENT_ID
const REDIRECT_URI   = import.meta.env.VITE_COGNITO_REDIRECT_URI  // e.g. https://app.example.com/callback

const REFRESH_KEY    = 'firefly_refresh_token'
const VERIFIER_KEY   = 'firefly_pkce_verifier'

// In-memory token state shared across the whole app.
const _accessToken  = ref(null)
const _idToken      = ref(null)
const _userClaims   = ref(null)

// ---------------------------------------------------------------------------
// PKCE helpers
// ---------------------------------------------------------------------------

function _randomBytes(length) {
  const arr = new Uint8Array(length)
  crypto.getRandomValues(arr)
  return arr
}

function _base64url(bytes) {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '')
}

async function _generatePkce() {
  const verifier  = _base64url(_randomBytes(32))
  const hashBuf   = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  const challenge = _base64url(new Uint8Array(hashBuf))
  return { verifier, challenge }
}

// ---------------------------------------------------------------------------
// JWT decode (no signature verification — API Gateway handles that)
// ---------------------------------------------------------------------------

function _decodeJwt(token) {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
  } catch {
    return null
  }
}

function _isExpired(token) {
  const claims = _decodeJwt(token)
  if (!claims || !claims.exp) return true
  return Date.now() / 1000 >= claims.exp - 30   // 30 s buffer
}

// ---------------------------------------------------------------------------
// Token exchange
// ---------------------------------------------------------------------------

async function _exchangeCode(code) {
  const verifier = sessionStorage.getItem(VERIFIER_KEY)
  if (!verifier) throw new Error('PKCE verifier missing')
  sessionStorage.removeItem(VERIFIER_KEY)

  const params = new URLSearchParams({
    grant_type:    'authorization_code',
    client_id:     CLIENT_ID,
    code,
    redirect_uri:  REDIRECT_URI,
    code_verifier: verifier,
  })

  const res = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body:    params.toString(),
  })

  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Token exchange failed: ${err}`)
  }

  return res.json()
}

async function _refreshTokens() {
  const refreshToken = sessionStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return false

  const params = new URLSearchParams({
    grant_type:    'refresh_token',
    client_id:     CLIENT_ID,
    refresh_token: refreshToken,
  })

  const res = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body:    params.toString(),
  })

  if (!res.ok) {
    sessionStorage.removeItem(REFRESH_KEY)
    return false
  }

  const data = await res.json()
  _setTokens(data.access_token, data.id_token, data.refresh_token || refreshToken)
  return true
}

function _setTokens(accessToken, idToken, refreshToken) {
  _accessToken.value = accessToken
  _idToken.value     = idToken
  _userClaims.value  = _decodeJwt(idToken)
  if (refreshToken) {
    sessionStorage.setItem(REFRESH_KEY, refreshToken)
  }
}

function _clearTokens() {
  _accessToken.value = null
  _idToken.value     = null
  _userClaims.value  = null
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(VERIFIER_KEY)
}

// ---------------------------------------------------------------------------
// Public composable
// ---------------------------------------------------------------------------

export function useAuth() {
  const isAuthenticated = computed(() => !!_accessToken.value)

  const isSuperUser = computed(() => {
    const groups = _userClaims.value?.['cognito:groups']
    if (!groups) return false
    if (Array.isArray(groups)) return groups.includes('super_users')
    try { return JSON.parse(groups).includes('super_users') } catch { /* */ }
    return groups.split(/[\s,]+/).includes('super_users')
  })

  const userEmail = computed(() => _userClaims.value?.email ?? null)
  const userName  = computed(() => _userClaims.value?.name  ?? null)

  function getAccessToken() {
    return _accessToken.value
  }

  async function startLogin() {
    const { verifier, challenge } = await _generatePkce()
    sessionStorage.setItem(VERIFIER_KEY, verifier)

    const params = new URLSearchParams({
      response_type:         'code',
      client_id:             CLIENT_ID,
      redirect_uri:          REDIRECT_URI,
      scope:                 'openid email profile',
      code_challenge:        challenge,
      code_challenge_method: 'S256',
      identity_provider:     'Google',
    })

    window.location.href = `${COGNITO_DOMAIN}/oauth2/authorize?${params}`
  }

  async function handleCallback(code) {
    const data = await _exchangeCode(code)
    _setTokens(data.access_token, data.id_token, data.refresh_token)
    await router.push('/firmware')
  }

  async function ensureAuthenticated() {
    // Already have a valid token in memory
    if (_accessToken.value && !_isExpired(_accessToken.value)) return true
    // Try refresh
    return _refreshTokens()
  }

  async function logout() {
    _clearTokens()
    const params = new URLSearchParams({
      client_id:   CLIENT_ID,
      logout_uri:  `${window.location.origin}/login`,
    })
    window.location.href = `${COGNITO_DOMAIN}/logout?${params}`
  }

  return {
    isAuthenticated,
    isSuperUser,
    userEmail,
    userName,
    getAccessToken,
    startLogin,
    handleCallback,
    ensureAuthenticated,
    logout,
  }
}
