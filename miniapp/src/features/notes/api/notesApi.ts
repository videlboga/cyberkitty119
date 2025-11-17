import type { Note, NoteAttachmentType, NoteFilters, NoteType, NotesResponse } from '../types'
import { apiClient } from '@/lib/api-client'
import { mockNotes } from '@/mocks/notes'
import { applyFilters } from '../utils/applyFilters'

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

let localNotes = [...mockNotes]

type ApiNoteGroup = {
  id: number
  name: string
  color?: string | null
}

type ApiNoteAttachment = {
  id: string | number
  name?: string | null
  type?: string | null
  url?: string | null
}

type ApiNote = {
  id: number
  title?: string | null
  summary?: string | null
  content?: string | null
  tags?: string[] | null
  groupIds?: number[] | null
  groups?: ApiNoteGroup[] | null
  status?: string | null
  type?: string | null
  createdAt: string
  updatedAt: string
  scheduledAt?: string | null
  color?: string | null
  attachments?: ApiNoteAttachment[] | null
  source?: string | null
}

type ApiNotesResponse = {
  items: ApiNote[]
  total: number
  page: number
  pageSize: number
  availableTags?: string[]
}

type ApiNoteDetailResponse = {
  note: ApiNote
}

const VALID_NOTE_TYPES: NoteType[] = ['task', 'meeting', 'idea', 'summary', 'reminder', 'note']

const ensureNoteType = (value?: string | null): NoteType => {
  if (!value) return 'note'
  const normalised = value.toLowerCase()
  return VALID_NOTE_TYPES.find((type) => type === normalised) ?? 'note'
}

const ensureAttachmentType = (value?: string | null): NoteAttachmentType => {
  if (value === 'audio' || value === 'file' || value === 'link') return value
  return 'file'
}

const toClientNote = (note: ApiNote): Note => {
  const groups = note.groups ?? []
  const targetGroupIds = note.groupIds ?? groups.map((group) => group.id)

  return {
    id: String(note.id),
    title: note.title ?? '',
    summary: note.summary ?? '',
    content: note.content ?? '',
    tags: note.tags ?? [],
    groupIds: targetGroupIds.map((groupId) => String(groupId)),
    type: ensureNoteType(note.type),
    createdAt: note.createdAt,
    updatedAt: note.updatedAt,
    scheduledAt: note.scheduledAt ?? undefined,
    color: note.color ?? null,
    attachments: (note.attachments ?? []).map((attachment) => ({
      id: String(attachment.id),
      name: attachment.name ?? 'Вложение',
      type: ensureAttachmentType(attachment.type),
      url: attachment.url ?? null,
    })),
    status: note.status ?? null,
    source: note.source ?? null,
    groups: groups.map((group) => ({
      id: String(group.id),
      name: group.name,
      color: group.color ?? null,
    })),
  }
}

const toServerPayload = (payload: Partial<Note>) => {
  const body: Record<string, unknown> = {}

  if (payload.title !== undefined) body.title = payload.title
  if (payload.summary !== undefined) body.summary = payload.summary
  if (payload.content !== undefined) body.content = payload.content
  if (payload.tags !== undefined) body.tags = payload.tags
  if (payload.status !== undefined) body.status = payload.status
  if (payload.type !== undefined) body.type = payload.type
  if (payload.scheduledAt !== undefined) body.scheduledAt = payload.scheduledAt
  if (payload.color !== undefined) body.color = payload.color

  if (payload.groupIds !== undefined) {
    const numericIds = payload.groupIds
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value))
    body.groupIds = numericIds
  }

  return body
}

const paginate = (items: Note[], page = 1, pageSize = 25): NotesResponse => {
  const start = (page - 1) * pageSize
  const end = start + pageSize
  return {
    items: items.slice(start, end),
    total: items.length,
    page,
    pageSize,
  }
}

export const notesApi = {
  async fetchNotes(filters: NoteFilters, page = 1, pageSize = 25) {
    if (USE_MOCK_DATA) {
      const filtered = applyFilters(localNotes, filters)
      return paginate(filtered, page, pageSize)
    }

    const response = await apiClient<ApiNotesResponse>('/notes', {
      params: {
        page,
        pageSize,
        period: filters.period,
        dateFrom: filters.dateFrom,
        dateTo: filters.dateTo,
        groupId: filters.groupId === 'all' ? undefined : filters.groupId ? Number(filters.groupId) : undefined,
        // type: filters.type === 'all' ? undefined : filters.type,
        tags: filters.tags?.join(','),
        search: filters.search,
      },
    })

    return {
      items: response.items.map(toClientNote),
      total: response.total,
      page: response.page,
      pageSize: response.pageSize,
      availableTags: response.availableTags ?? [],
    }
  },

  async fetchNote(id: string) {
    if (USE_MOCK_DATA) {
      const note = localNotes.find((item) => item.id === id)
      if (!note) throw new Error('Заметка не найдена')
      return note
    }
    const response = await apiClient<ApiNoteDetailResponse>(`/notes/${id}`)
    return toClientNote(response.note)
  },

  async createNote(payload: Partial<Note>) {
    if (USE_MOCK_DATA) {
      const now = new Date().toISOString()
      const generatedId =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `note-${Date.now()}`
      const newNote: Note = {
        id: generatedId,
        title: payload.title ?? 'Новая заметка',
        summary: payload.summary ?? '',
        content: payload.content ?? '',
        tags: payload.tags ?? [],
        groupIds: payload.groupIds ?? [],
        type: payload.type ?? 'idea',
        createdAt: now,
        updatedAt: now,
        scheduledAt: payload.scheduledAt,
        color: payload.color,
        attachments: payload.attachments ?? [],
      }
      localNotes = [newNote, ...localNotes]
      return newNote
    }

    const response = await apiClient<ApiNoteDetailResponse>('/notes', {
      method: 'POST',
      body: JSON.stringify(toServerPayload(payload)),
    })
    return toClientNote(response.note)
  },

  async updateNote(id: string, payload: Partial<Note>) {
    if (USE_MOCK_DATA) {
      const idx = localNotes.findIndex((item) => item.id === id)
      if (idx === -1) throw new Error('Заметка не найдена')
      const updated: Note = {
        ...localNotes[idx],
        ...payload,
        updatedAt: new Date().toISOString(),
      }
      localNotes[idx] = updated
      return updated
    }

    const response = await apiClient<ApiNoteDetailResponse>(`/notes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(toServerPayload(payload)),
    })
    return toClientNote(response.note)
  },

  async deleteNote(id: string) {
    if (USE_MOCK_DATA) {
      localNotes = localNotes.filter((item) => item.id !== id)
      return
    }

    await apiClient(`/notes/${id}`, {
      method: 'DELETE',
    })
  },
}
