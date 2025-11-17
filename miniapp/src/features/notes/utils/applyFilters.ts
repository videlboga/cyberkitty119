import {
  endOfDay,
  endOfMonth,
  endOfToday,
  endOfWeek,
  isWithinInterval,
  parseISO,
  startOfMonth,
  startOfToday,
  startOfWeek,
} from 'date-fns'
import type { Note, NoteFilters } from '../types'

const toDate = (value?: string) => {
  if (!value) return undefined
  try {
    return parseISO(value)
  } catch (error) {
    console.warn('Failed to parse date', value, error)
    return undefined
  }
}

const resolveInterval = (filters: NoteFilters) => {
  const now = new Date()
  switch (filters.period) {
    case 'today':
      return { start: startOfToday(), end: endOfToday() }
    case 'week':
      return { start: startOfWeek(now, { weekStartsOn: 1 }), end: endOfWeek(now, { weekStartsOn: 1 }) }
    case 'month':
      return { start: startOfMonth(now), end: endOfMonth(now) }
    case 'custom':
      return {
        start: toDate(filters.dateFrom) ?? startOfToday(),
        end: filters.dateTo ? endOfDay(toDate(filters.dateTo) ?? new Date()) : endOfToday(),
      }
    default:
      return { start: startOfWeek(now, { weekStartsOn: 1 }), end: endOfWeek(now, { weekStartsOn: 1 }) }
  }
}

export const applyFilters = (notes: Note[], filters: NoteFilters) => {
  const interval = resolveInterval(filters)
  const searchQuery = filters.search?.trim().toLowerCase()
  const tags = filters.tags ?? []

  return notes.filter((note) => {
    const scheduled = toDate(note.scheduledAt)
    const created = toDate(note.createdAt)
    const targetDate = scheduled ?? created

    if (targetDate && !isWithinInterval(targetDate, interval)) {
      return false
    }

    if (filters.groupId && filters.groupId !== 'all' && !note.groupIds.includes(filters.groupId)) {
      return false
    }

    // if (filters.type && filters.type !== 'all' && note.type !== filters.type) {
    //   return false
    // }

    if (tags.length && !tags.every((tag) => note.tags.includes(tag))) {
      return false
    }

    if (searchQuery) {
      const haystack = [note.title, note.summary, note.content, note.tags.join(' ')].join(' ').toLowerCase()
      if (!haystack.includes(searchQuery)) {
        return false
      }
    }

    return true
  })
}
