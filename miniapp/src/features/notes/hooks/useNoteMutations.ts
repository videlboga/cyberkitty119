import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Note } from '../types'
import { notesApi } from '../api/notesApi'
import { notesQueryKey } from './useNotesQuery'

export const useCreateNoteMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: Partial<Note>) => notesApi.createNote(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notesQueryKey })
    },
  })
}

export const useUpdateNoteMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Note> }) =>
      notesApi.updateNote(id, data),
    onSuccess: (_note, variables) => {
      queryClient.invalidateQueries({ queryKey: notesQueryKey })
      queryClient.invalidateQueries({ queryKey: ['note', variables.id] })
    },
  })
}

export const useDeleteNoteMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => notesApi.deleteNote(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notesQueryKey })
    },
  })
}
