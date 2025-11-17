import { apiClient } from '@/lib/api-client'

const resolveBaseUrl = (rawBase: string) => {
  const base = rawBase.trim() || '/'
  if (/^https?:\/\//i.test(base)) {
    return base.replace(/\/?$/, '/')
  }
  if (typeof window !== 'undefined') {
    const suffix = base.replace(/\/?$/, '/').replace(/^\/+/, '')
    if (base.startsWith('/')) {
      return `${window.location.origin}/${suffix}`
    }
    return `${window.location.origin}/${suffix}`
  }
  return base
}

const buildEndpointUrl = (path: string) => {
  const rawBase = import.meta.env.VITE_API_URL ?? '/api/miniapp'
  const base = resolveBaseUrl(rawBase)
  const normalizedPath = path.replace(/^\//, '')
  return new URL(normalizedPath, base).toString()
}

export type AgentMessageRole = 'user' | 'assistant' | 'system'

export interface AgentHistoryItem {
  role: AgentMessageRole
  content: string
}

export interface AgentActiveNote {
  id: string
  summary?: string
  title?: string
  type?: string
}

export interface AgentSessionState {
  messages: AgentHistoryItem[]
  activeNote?: AgentActiveNote
  suggestions: string[]
}

type ServerAgentHistoryItem = {
  role?: string | null
  content?: string | null
}

type ServerAgentActiveNote = {
  id: number
  summary?: string | null
  title?: string | null
  type?: string | null
}

type ServerAgentSession = {
  messages?: ServerAgentHistoryItem[]
  activeNote?: ServerAgentActiveNote | null
  suggestions?: string[] | null
}

const normaliseSession = (payload: ServerAgentSession): AgentSessionState => {
  const messages: AgentHistoryItem[] = []
  for (const item of payload.messages ?? []) {
    const role = (item.role ?? '').toLowerCase()
    const content = (item.content ?? '').trim()
    if (!content) continue
    if (role === 'assistant' || role === 'ai') {
      messages.push({ role: 'assistant', content })
    } else if (role === 'system') {
      messages.push({ role: 'system', content })
    } else {
      messages.push({ role: 'user', content })
    }
  }

  let active: AgentActiveNote | undefined
  const activeSource = payload.activeNote
  if (activeSource) {
    active = {
      id: String(activeSource.id),
      summary: activeSource.summary ?? undefined,
      title: activeSource.title ?? undefined,
      type: activeSource.type ?? undefined,
    }
  }

  const suggestions = (payload.suggestions ?? []).filter((item): item is string => Boolean(item && item.trim()))

  return {
    messages,
    activeNote: active,
    suggestions,
  }
}

export const agentApi = {
  async fetchSession(): Promise<AgentSessionState> {
    const response = await apiClient<ServerAgentSession>('/agent/session')
    return normaliseSession(response)
  },

  async sendMessage(message: string, noteId?: string | null): Promise<AgentSessionState> {
    const response = await apiClient<ServerAgentSession>('/agent/messages', {
      method: 'POST',
      body: JSON.stringify({
        message,
        noteId: noteId ? Number(noteId) : undefined,
      }),
    })
    return normaliseSession(response)
  },

  async activateNote(noteId: string): Promise<AgentSessionState> {
    const response = await apiClient<ServerAgentSession>('/agent/activate', {
      method: 'POST',
      body: JSON.stringify({ noteId: Number(noteId) }),
    })
    return normaliseSession(response)
  },

  async uploadMedia(
    file: File,
    noteId: string | null,
    onProgress?: (phase: 'upload' | 'processing', value?: number) => void,
  ): Promise<AgentSessionState> {
    const formData = new FormData()
    formData.append('file', file, file.name)
    if (noteId) {
      formData.append('noteId', noteId)
    }

    const url = buildEndpointUrl('/agent/upload')
    const token =
      typeof window !== 'undefined'
        ? window.localStorage?.getItem('miniapp-token') ?? undefined
        : undefined

    return new Promise<AgentSessionState>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', url, true)
      xhr.withCredentials = true
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      }

      xhr.upload.onprogress = (event) => {
        if (!onProgress) return
        if (event.lengthComputable) {
          const ratio = event.total > 0 ? event.loaded / event.total : 0
          onProgress('upload', Math.max(0, Math.min(1, ratio)))
        } else {
          onProgress('upload')
        }
      }

      xhr.upload.onload = () => {
        onProgress?.('processing')
      }

      xhr.onreadystatechange = () => {
        if (xhr.readyState !== XMLHttpRequest.DONE) return
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText) as ServerAgentSession
            resolve(normaliseSession(data))
          } catch (error) {
            reject(error)
          }
        } else {
          reject(new Error(xhr.responseText || `Upload failed with status ${xhr.status}`))
        }
      }

      xhr.onerror = () => {
        reject(new Error('Сеть недоступна. Попробуйте ещё раз.'))
      }

      xhr.send(formData)
    })
  },
}
