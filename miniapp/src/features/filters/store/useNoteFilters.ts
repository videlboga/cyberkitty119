import { create } from 'zustand'
import type { NoteType } from '../../notes/types'

export type Period = 'today' | 'week' | 'month' | 'custom'

interface NoteFiltersState {
  period: Period
  dateFrom?: string
  dateTo?: string
  groupId: string | 'all'
  type: NoteType | 'all'
  tags: string[]
  search: string
  setPeriod: (period: Period) => void
  setDateRange: (from?: string, to?: string) => void
  setGroupId: (groupId: NoteFiltersState['groupId']) => void
  setType: (type: NoteFiltersState['type']) => void
  toggleTag: (tag: string) => void
  setTags: (tags: string[]) => void
  setSearch: (value: string) => void
  reset: () => void
}

const initialState: Omit<
  NoteFiltersState,
  'setPeriod' | 'setDateRange' | 'setGroupId' | 'setType' | 'toggleTag' | 'setTags' | 'setSearch' | 'reset'
> = {
  period: 'week',
  groupId: 'all',
  type: 'all',
  tags: [],
  search: '',
}

export const useNoteFilters = create<NoteFiltersState>((set) => ({
  ...initialState,
  setPeriod: (period) =>
    set((state) => ({
      period,
      dateFrom: period !== 'custom' ? undefined : state.dateFrom,
      dateTo: period !== 'custom' ? undefined : state.dateTo,
    })),
  setDateRange: (from, to) =>
    set(() => ({
      dateFrom: from,
      dateTo: to,
      period: 'custom',
    })),
  setGroupId: (groupId) => set(() => ({ groupId })),
  setType: (type) => set(() => ({ type })),
  toggleTag: (tag) =>
    set((state) => ({
      tags: state.tags.includes(tag)
        ? state.tags.filter((item) => item !== tag)
        : [...state.tags, tag],
    })),
  setTags: (tags) => set(() => ({ tags })),
  setSearch: (value) => set(() => ({ search: value })),
  reset: () => set(() => ({ ...initialState })),
}))
