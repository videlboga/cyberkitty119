import { useQuery } from '@tanstack/react-query'
import type { Note } from '../types'
import { notesApi } from '../api/notesApi'

export const useNoteQuery = (id?: string) =>
  useQuery<Note, Error>({
    queryKey: ['note', id],
    queryFn: () => {
      if (!id) throw new Error('Не указан идентификатор заметки')
      return notesApi.fetchNote(id)
    },
    enabled: Boolean(id),
  })
