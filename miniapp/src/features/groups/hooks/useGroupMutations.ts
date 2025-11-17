import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Group } from '../types'
import { groupsApi } from '../api/groupsApi'

const GROUPS_KEY = ['groups'] as const

export const useCreateGroupMutation = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Pick<Group, 'name' | 'color' | 'tags'>) =>
      groupsApi.createGroup(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}

export const useUpdateGroupMutation = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Group> }) =>
      groupsApi.updateGroup(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}

export const useDeleteGroupMutation = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => groupsApi.deleteGroup(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}

export const useMergeGroupMutation = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ids, name, color }: { ids: string[]; name: string; color: string }) =>
      groupsApi.mergeGroups(ids, { name, color }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}
