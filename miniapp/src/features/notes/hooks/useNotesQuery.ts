import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useNoteFilters } from '@/features/filters/store/useNoteFilters'
import { notesApi } from '../api/notesApi'
import type { NotesResponse } from '../types'

const NOTES_QUERY_KEY = ['notes'] as const

export const useNotesQuery = (page = 1, pageSize = 25) => {
  const period = useNoteFilters((state) => state.period)
  const dateFrom = useNoteFilters((state) => state.dateFrom)
  const dateTo = useNoteFilters((state) => state.dateTo)
  const groupId = useNoteFilters((state) => state.groupId)
  // const type = useNoteFilters((state) => state.type)
  const tags = useNoteFilters((state) => state.tags)
  const search = useNoteFilters((state) => state.search)

  const filters = useMemo(
    () => ({ period, dateFrom, dateTo, groupId, tags, search }),
    [period, dateFrom, dateTo, groupId, tags, search],
  )

  const queryKey = useMemo(() => [...NOTES_QUERY_KEY, { ...filters, page, pageSize }], [filters, page, pageSize])

  return useQuery<NotesResponse, Error>({
    queryKey,
    queryFn: () => notesApi.fetchNotes({ ...filters }, page, pageSize),
    placeholderData: (previousData) => previousData,
  })
}

export const notesQueryKey = NOTES_QUERY_KEY
