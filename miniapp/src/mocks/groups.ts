import type { Group, GroupSuggestion } from '@/features/groups/types'

export const mockGroups: Group[] = [
  {
    id: 'group-001',
    name: 'Продукт',
    color: '#6366f1',
    tags: ['roadmap', 'release', 'product'],
    noteCount: 6,
    updatedAt: new Date().toISOString(),
  },
  {
    id: 'group-002',
    name: 'Команда',
    color: '#22d3ee',
    tags: ['команда', 'созвон', 'аналитика'],
    noteCount: 4,
    updatedAt: new Date().toISOString(),
  },
  {
    id: 'group-003',
    name: 'AI идеи',
    color: '#f97316',
    tags: ['ai', 'исследование'],
    noteCount: 3,
    updatedAt: new Date().toISOString(),
  },
]

export const mockGroupSuggestions: GroupSuggestion[] = [
  {
    id: 'suggestion-ux',
    name: 'UX / UI',
    tags: ['ux', 'design'],
    confidence: 0.87,
  },
  {
    id: 'suggestion-calendar',
    name: 'Календарь',
    tags: ['календарь', 'meeting'],
    confidence: 0.74,
  },
  {
    id: 'suggestion-analytics',
    name: 'Analytics',
    tags: ['аналитика', 'infra'],
    confidence: 0.61,
  },
]
