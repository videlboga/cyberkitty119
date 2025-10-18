import { useQuery } from '@tanstack/react-query'
import { groupsApi } from '../api/groupsApi'
import type { Group } from '../types'

export const useGroupsQuery = () =>
  useQuery<Group[], Error>({
    queryKey: ['groups'],
    queryFn: () => groupsApi.fetchGroups(),
    staleTime: 120_000,
  })

export const useGroupSuggestionsQuery = () =>
  useQuery({
    queryKey: ['group-suggestions'],
    queryFn: () => groupsApi.fetchSuggestions(),
    staleTime: 300_000,
  })
