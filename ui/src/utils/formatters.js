export const STATUS_LABELS = {
  PROCESSING: 'Processing',
  READY_TO_TEST: 'Ready to Test',
  TESTING: 'Testing',
  RELEASED: 'Released',
  REVOKED: 'Revoked',
  DELETED: 'Deleted',
  ERROR: 'Error',
}

// Tailwind classes for each status badge
export const STATUS_STYLES = {
  PROCESSING: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  READY_TO_TEST: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
  TESTING: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  RELEASED: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
  REVOKED: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
  DELETED: 'bg-gray-50 text-gray-400 dark:bg-gray-800 dark:text-gray-500',
  ERROR: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
}

// Dot color for status badge
export const STATUS_DOT = {
  PROCESSING: 'bg-gray-400',
  READY_TO_TEST: 'bg-amber-400',
  TESTING: 'bg-blue-400',
  RELEASED: 'bg-green-400',
  REVOKED: 'bg-orange-400',
  DELETED: 'bg-gray-300 dark:bg-gray-600',
  ERROR: 'bg-red-400',
}

// Which status each state can transition TO (null = no transition)
export const VALID_TRANSITIONS = {
  READY_TO_TEST: 'TESTING',
  TESTING: 'RELEASED',
  RELEASED: 'REVOKED',
}

export const TRANSITION_BUTTON_LABELS = {
  READY_TO_TEST: 'Move Back to Ready to Test',
  TESTING: 'Move to Testing',
  RELEASED: 'Release',
  REVOKED: 'Revoke',
}

// Which status each state can roll BACK to (null = no rollback)
export const ROLLBACK_TRANSITIONS = {
  TESTING: 'READY_TO_TEST',
}

// Transitions that require a confirmation dialog
export const TRANSITIONS_REQUIRING_CONFIRM = new Set(['RELEASED', 'REVOKED'])

// States that cannot be deleted via the API (409)
export const NON_DELETABLE_STATES = new Set(['DELETED', 'REVOKED', 'RELEASED'])

export function formatClass(value) {
  if (!value) return '—'
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()
}

export function formatBytes(bytes) {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Coerce value to a Date. Handles numbers (unix seconds), numeric strings
// (DynamoDB Decimal serialized via json.dumps default=str), and ISO strings.
function toDate(value) {
  if (typeof value === 'number') return new Date(value * 1000)
  if (typeof value === 'string' && /^\d+$/.test(value)) return new Date(Number(value) * 1000)
  return new Date(value)
}

// value: ISO string, unix timestamp (seconds), or numeric string
export function formatAbsoluteDate(value) {
  if (!value) return '—'
  const date = toDate(value)
  return new Intl.DateTimeFormat(navigator.language, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    timeZoneName: 'short',
  }).format(date)
}

export function formatRelativeDate(value) {
  if (!value) return '—'
  const date = toDate(value)
  const diffMs = Date.now() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)
  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 30) return `${diffDay}d ago`
  return formatAbsoluteDate(value)
}
