import { apiClient } from '@/lib/api-client'
import { mockGroupSuggestions, mockGroups } from '@/mocks/groups'
import type { Group, GroupSuggestion } from '../types'

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

let localGroups = [...mockGroups]

const nextId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `group-${Date.now()}`

type ApiGroup = {
  id: number
  name: string
  color?: string | null
  tags?: string[] | null
  noteCount: number
  updatedAt: string
}

const toClientGroup = (group: ApiGroup): Group => ({
  id: String(group.id),
  name: group.name,
  color: group.color ?? null,
  tags: group.tags ?? [],
  noteCount: group.noteCount ?? 0,
  updatedAt: group.updatedAt,
})

const toNumericIds = (ids: string[]) =>
  ids
    .map((id) => Number(id))
    .filter((id) => Number.isFinite(id))

export const groupsApi = {
  async fetchGroups() {
    if (USE_MOCK_DATA) {
      return localGroups
    }
    const groups = await apiClient<ApiGroup[]>('/groups')
    return groups.map(toClientGroup)
  },

  async createGroup(payload: Pick<Group, 'name' | 'color' | 'tags'>) {
    if (USE_MOCK_DATA) {
      const newGroup: Group = {
        id: nextId(),
        name: payload.name,
        color: payload.color,
        tags: payload.tags,
        noteCount: 0,
        updatedAt: new Date().toISOString(),
      }
      localGroups = [newGroup, ...localGroups]
      return newGroup
    }

    const response = await apiClient<ApiGroup>('/groups', {
      method: 'POST',
      body: JSON.stringify({
        name: payload.name,
        color: payload.color,
        tags: payload.tags,
      }),
    })
    return toClientGroup(response)
  },

  async updateGroup(id: string, payload: Partial<Group>) {
    if (USE_MOCK_DATA) {
      const index = localGroups.findIndex((group) => group.id === id)
      if (index === -1) throw new Error('Группа не найдена')
      const updated: Group = {
        ...localGroups[index],
        ...payload,
        updatedAt: new Date().toISOString(),
      }
      localGroups[index] = updated
      return updated
    }

    const response = await apiClient<ApiGroup>(`/groups/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: payload.name,
        color: payload.color,
        tags: payload.tags,
      }),
    })
    return toClientGroup(response)
  },

  async deleteGroup(id: string) {
    if (USE_MOCK_DATA) {
      localGroups = localGroups.filter((group) => group.id !== id)
      return
    }

    await apiClient(`/groups/${id}`, { method: 'DELETE' })
  },

  async mergeGroups(ids: string[], payload: { name: string; color: string }) {
    if (USE_MOCK_DATA) {
      const groups = localGroups.filter((group) => ids.includes(group.id))
      const mergedTags = Array.from(new Set(groups.flatMap((group) => group.tags)))
      const mergedCount = groups.reduce((acc, item) => acc + item.noteCount, 0)
      const mergedGroup: Group = {
        id: nextId(),
        name: payload.name,
        color: payload.color,
        tags: mergedTags,
        noteCount: mergedCount,
        updatedAt: new Date().toISOString(),
      }
      localGroups = [mergedGroup, ...localGroups.filter((group) => !ids.includes(group.id))]
      return mergedGroup
    }

    const response = await apiClient<ApiGroup>('/groups/merge', {
      method: 'POST',
      body: JSON.stringify({
        ids: toNumericIds(ids),
        name: payload.name,
        color: payload.color,
      }),
    })
    return toClientGroup(response)
  },

  async fetchSuggestions() {
    if (USE_MOCK_DATA) {
      return mockGroupSuggestions
    }
    return apiClient<GroupSuggestion[]>('/groups/suggestions')
  },
}
