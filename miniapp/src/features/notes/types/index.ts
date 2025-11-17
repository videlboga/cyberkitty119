export type NoteType = 'idea' | 'task' | 'meeting' | 'summary' | 'reminder' | 'note'

export type NoteAttachmentType = 'audio' | 'file' | 'link'

export interface NoteAttachment {
  id: string
  name: string
  type: NoteAttachmentType
  url?: string | null
}

export interface Note {
  id: string
  title: string
  summary: string
  content: string
  tags: string[]
  groupIds: string[]
  type: NoteType
  createdAt: string
  updatedAt: string
  scheduledAt?: string
  archivedAt?: string
  color?: string | null
  attachments?: NoteAttachment[]
  status?: string | null
  source?: string | null
  groups?: Array<{
    id: string
    name: string
    color?: string | null
  }>
}

export interface NoteFilters {
  period: 'today' | 'week' | 'month' | 'custom'
  dateFrom?: string
  dateTo?: string
  groupId?: string | 'all'
  type?: NoteType | 'all'
  tags?: string[]
  search?: string
}

export interface NotesResponse {
  items: Note[]
  total: number
  page: number
  pageSize: number
  availableTags?: string[]
}
