/**
 * Time utilities for consistent timezone handling.
 * Server timestamps are in UTC but may not include 'Z' suffix.
 */

// Parse timestamp as UTC (server sends UTC without 'Z' suffix)
export function parseAsUTC(timestamp: string): Date {
  // If timestamp doesn't have timezone info, treat as UTC
  if (!timestamp.endsWith('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
    return new Date(timestamp + 'Z')
  }
  return new Date(timestamp)
}

// Format to local time (HH:MM:SS)
export function formatLocalTime(timestamp: string | null | undefined): string {
  if (!timestamp) return ''
  const date = parseAsUTC(timestamp)
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// Format to local date/time - shows time only if today, otherwise date + time
export function formatLocalDateTime(timestamp: string | null | undefined): string {
  if (!timestamp) return ''
  const date = parseAsUTC(timestamp)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// Format to local date only (e.g., "Jan 18" or "Jan 18, 2024")
export function formatLocalDate(timestamp: string | null | undefined, includeYear = false): string {
  if (!timestamp) return ''
  const date = parseAsUTC(timestamp)

  if (includeYear) {
    return date.toLocaleDateString([], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }
  return date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  })
}

// Format full local date/time
export function formatLocalFull(timestamp: string | null | undefined): string {
  if (!timestamp) return ''
  const date = parseAsUTC(timestamp)
  return date.toLocaleString()
}

// Format as relative time (e.g., "2h ago", "3d ago")
export function formatRelativeTime(timestamp: string | null | undefined, defaultValue: string = ''): string {
  if (!timestamp) return defaultValue
  const date = parseAsUTC(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 48) return `${diffHour}h ago`
  if (diffDay < 7) return `${diffDay}d ago`
  return formatLocalDate(timestamp)
}
