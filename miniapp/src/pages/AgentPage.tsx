import { IconInfoCircle, IconPaperclip, IconRobot, IconSend, IconUser } from '@tabler/icons-react'
import clsx from 'clsx'
import type { ChangeEvent, FormEvent, MouseEvent, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Card } from '@/components/common/Card'
import { Chip } from '@/components/common/Chip'
import { EmptyState } from '@/components/common/EmptyState'
import type { AgentActiveNote, AgentHistoryItem, AgentSessionState } from '@/features/agent/api/agentApi'
import { agentApi } from '@/features/agent/api/agentApi'
import { getBasePath } from '@/lib/basePath'
import { resolveStartParamToPath } from '@/lib/startParam'

const TELEGRAM_PROXY_HOSTS = new Set(['t.me', 'telegram.me', 'telegram.dog'])

const decodePayload = (value: string): string => {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

const resolveTelegramProxyLink = (rawHref: string): string | null => {
  if (!rawHref) {
    return null
  }

  let url: URL
  try {
    url = new URL(rawHref)
  } catch {
    try {
      url = new URL(rawHref, 'https://t.me')
    } catch {
      return null
    }
  }

  const host = url.host.toLowerCase()
  if (!TELEGRAM_PROXY_HOSTS.has(host)) {
    return null
  }

  const segments = url.pathname.split('/').filter(Boolean)

  const queryKeys = [
    'startapp',
    'start_app',
    'start_param',
    'startparam',
    'tgWebAppStartParam',
    'start',
  ]

  let queryPayload: string | null = null
  for (const key of queryKeys) {
    const candidate = url.searchParams.get(key)
    if (candidate) {
      queryPayload = candidate
      break
    }
  }

  let pathPayload = ''
  if (segments.length >= 2) {
    const routeKey = segments[1].toLowerCase()
    if (routeKey === 'journal' || routeKey === 'app' || routeKey === 'miniapp') {
      pathPayload = segments.slice(2).map(decodePayload).join('/')
    } else {
      pathPayload = ''
    }
  }

  const payload = queryPayload ?? pathPayload
  if (!payload) {
    return null
  }

  if (segments.length >= 2) {
    const routeKey = segments[1].toLowerCase()
    if (routeKey !== 'journal' && routeKey !== 'app' && routeKey !== 'miniapp') {
      return null
    }
  }

  return resolveStartParamToPath(payload)
}

const MAX_UPLOAD_SIZE_MB = 2048
const formatSizeLimit = () => {
  if (MAX_UPLOAD_SIZE_MB % 1024 === 0) {
    return `${MAX_UPLOAD_SIZE_MB / 1024} ГБ`
  }
  return `${MAX_UPLOAD_SIZE_MB} МБ`
}

type AgentMessage = AgentHistoryItem & { index: number; id: string }

const mapMessages = (items: AgentHistoryItem[]): AgentMessage[] =>
  items.map((message, index) => ({
    ...message,
    index,
    id: `server-${index}-${message.role}-${message.content.length}`,
  }))

const buildErrorMessage = (error: unknown) => {
  let raw = ''
  if (error instanceof Error && error.message) {
    raw = error.message
  } else if (typeof error === 'string') {
    raw = error
  }

  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (typeof parsed?.detail === 'string') {
        raw = parsed.detail
      }
    } catch (parseError) {
      void parseError
    }

    if (/<html/i.test(raw)) {
      if (/413/i.test(raw)) {
        return `Файл слишком большой. Максимум ${formatSizeLimit()}.`
      }
      return 'Сервис временно недоступен. Попробуйте ещё раз позже.'
    }

    return raw
  }

  return 'Что-то пошло не так. Попробуйте ещё раз.'
}

const createMessageId = () => `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

export const AgentPage = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [activeNote, setActiveNote] = useState<AgentActiveNote | undefined>()
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSending, setIsSending] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingMessages, setPendingMessages] = useState<AgentMessage[]>([])
  const [uploadPhase, setUploadPhase] = useState<'idle' | 'upload' | 'processing'>('idle')
  const [uploadProgress, setUploadProgress] = useState<number | undefined>(undefined)
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const conversation = useMemo(() => [...messages, ...pendingMessages], [messages, pendingMessages])
  const detectedBasePath = getBasePath()
  const basePath = detectedBasePath === '/' ? '' : detectedBasePath

  const resolveInternalPath = useCallback(
    (href: string): string | null => {
      if (!href) return null
      let candidate = href.trim()

      const telegramTarget = resolveTelegramProxyLink(candidate)
      if (telegramTarget) {
        return telegramTarget
      }

      try {
        const url = new URL(candidate, window.location.origin)
        if (url.origin !== window.location.origin) {
          return null
        }
        candidate = url.pathname
      } catch {
        if (!candidate.startsWith('/')) {
          if (candidate.startsWith('notes/')) {
            candidate = `/${candidate}`
          } else {
            return null
          }
        }
      }

      if (basePath && candidate.startsWith(basePath)) {
        candidate = candidate.slice(basePath.length)
        if (!candidate.startsWith('/')) {
          candidate = `/${candidate}`
        }
      }

      if (!candidate.startsWith('/')) {
        candidate = `/${candidate}`
      }

      if (candidate === '/' || candidate.startsWith('/notes/')) {
        return candidate
      }

      const allowed = ['/assistant', '/groups', '/settings']
      if (allowed.some((prefix) => candidate === prefix || candidate.startsWith(`${prefix}/`))) {
        return candidate
      }

      return null
    },
    [basePath],
  )

  const renderLineWithLinks = useCallback(
    (line: string, key: string): ReactNode => {
      const nodes: ReactNode[] = []
      const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g
      let lastIndex = 0
      let match: RegExpExecArray | null

      while ((match = linkRegex.exec(line)) !== null) {
        if (match.index > lastIndex) {
          nodes.push(<span key={`${key}-text-${nodes.length}`}>{line.slice(lastIndex, match.index)}</span>)
        }

        const label = match[1]
        const href = match[2]
        const internalPath = resolveInternalPath(href)

        const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
          if (!internalPath) return
          event.preventDefault()
          navigate(internalPath)
        }

        nodes.push(
          <a
            key={`${key}-link-${nodes.length}`}
            href={internalPath ?? href}
            onClick={handleClick}
            target={internalPath ? undefined : '_blank'}
            rel={internalPath ? undefined : 'noopener noreferrer'}
          >
            {label}
          </a>,
        )

        lastIndex = match.index + match[0].length
      }

      if (lastIndex < line.length) {
        nodes.push(<span key={`${key}-text-${nodes.length}`}>{line.slice(lastIndex)}</span>)
      }

      if (nodes.length === 0) {
        nodes.push(<span key={`${key}-text-0`}>{line}</span>)
      }

      return nodes
    },
    [navigate, resolveInternalPath],
  )

  const renderMessageContent = useCallback(
    (text: string): ReactNode => {
      const lines = text.split(/\r?\n/)
      return lines.reduce<ReactNode[]>((acc, line, index) => {
        const isLastLine = index === lines.length - 1
        if (!line) {
          if (!isLastLine) {
            acc.push(<br key={`empty-${index}`} />)
          }
          return acc
        }

        const key = `line-${index}`
        acc.push(
          <span key={key}>
            {renderLineWithLinks(line, key)}
            {!isLastLine && <br />}
          </span>,
        )
        return acc
      }, [])
    },
    [renderLineWithLinks],
  )

  const applySessionState = useCallback((state: AgentSessionState) => {
    setMessages(mapMessages(state.messages))
    setActiveNote(state.activeNote)
    setSuggestions(state.suggestions)
    setPendingMessages([])
  }, [])

  useEffect(() => {
    let cancelled = false
    const bootstrap = async () => {
      setIsLoading(true)
      try {
        const session = await agentApi.fetchSession()
        if (cancelled) return
        applySessionState(session)
        setError(null)
      } catch (err) {
        if (!cancelled) {
          setError(buildErrorMessage(err))
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [applySessionState])

  useEffect(() => {
    const main = document.querySelector<HTMLElement>('main.app-content, main.app-editor')
    main?.classList.add('app-shell--agent')
    return () => {
      main?.classList.remove('app-shell--agent')
    }
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const noteParam = params.get('note')
    if (!noteParam) return

    const activate = async () => {
      try {
        const numericId = Number(noteParam)
        if (!Number.isFinite(numericId) || numericId <= 0) {
          throw new Error('Некорректный идентификатор заметки')
        }
        const session = await agentApi.activateNote(String(numericId))
        applySessionState(session)
        setError(null)
      } catch (err) {
        setError(buildErrorMessage(err))
      } finally {
        navigate('/assistant', { replace: true })
      }
    }

    void activate()
  }, [applySessionState, location.search, navigate])

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, pendingMessages.length])

  const handleSend = useCallback(
    async (event?: FormEvent<HTMLFormElement>) => {
      event?.preventDefault()
      const trimmed = inputValue.trim()
      if (!trimmed || isSending || isUploading) return

      const statusId = createMessageId()
      const userId = createMessageId()
      setPendingMessages((prev) => {
        const base = messages.length + prev.length
        return [
          ...prev,
          { role: 'user', content: trimmed, index: base, id: userId },
          { role: 'system', content: '⏳ Думаю…', index: base + 1, id: statusId },
        ]
      })

      setInputValue('')
      setIsSending(true)
      try {
        const session = await agentApi.sendMessage(trimmed, activeNote?.id ?? null)
        applySessionState(session)
        setError(null)
      } catch (err) {
        const message = buildErrorMessage(err)
        setError(message)
        setInputValue(trimmed)
        setPendingMessages((prev) =>
          prev.map((item) =>
            item.id === statusId ? { ...item, content: `⚠️ ${message}` } : item,
          ),
        )
      } finally {
        setIsSending(false)
      }
    },
    [activeNote?.id, applySessionState, inputValue, isSending, isUploading, messages.length]
  )

  const handleSuggestion = useCallback(
    (value: string) => {
      setInputValue(value)
      inputRef.current?.focus()
    },
    []
  )

  const handleFileChange = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file || isSending || isUploading) {
        event.target.value = ''
        return
      }

      const maxBytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
      if (file.size > maxBytes) {
        event.target.value = ''
        const message = `Файл больше ${formatSizeLimit()}. Загрузите файл меньшего размера.`
        setError(message)
        setPendingMessages((prev) => [
          ...prev,
          {
            role: 'system',
            content: `⚠️ ${message}`,
            index: messages.length + prev.length,
            id: createMessageId(),
          },
        ])
        return
      }

      event.target.value = ''
      setIsUploading(true)
      setUploadPhase('upload')
      setUploadProgress(0)
      setError(null)
      try {
        const session = await agentApi.uploadMedia(file, activeNote?.id ?? null, (phase, value) => {
          if (phase === 'upload') {
            setUploadPhase('upload')
            if (typeof value === 'number') {
              setUploadProgress(value)
            }
          } else if (phase === 'processing') {
            setUploadPhase('processing')
            setUploadProgress(undefined)
          }
        })
        applySessionState(session)
        setError(null)
      } catch (err) {
        const message = buildErrorMessage(err)
        setError(message)
      } finally {
        setIsUploading(false)
        setUploadPhase('idle')
        setUploadProgress(undefined)
      }
    },
    [activeNote?.id, applySessionState, isSending, isUploading, messages.length]
  )

  const triggerFileDialog = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const emptyState = useMemo(() => {
    if (!isLoading || messages.length > 0) return null
    if (error) {
      return (
        <EmptyState
          title="Не удалось загрузить диалог"
          description={error}
          action={
            <button
              type="button"
              className="ui-button"
              onClick={() => {
                setError(null)
                setIsLoading(true)
                agentApi
                  .fetchSession()
                  .then((session) => {
                    applySessionState(session)
                    setError(null)
                  })
                  .catch((err) => setError(buildErrorMessage(err)))
                  .finally(() => setIsLoading(false))
              }}
            >
              Повторить
            </button>
          }
        />
      )
    }
    return (
      <Card className="agent-page__placeholder">
        <p>ИИ-агент поможет найти или обновить заметки. Задайте вопрос или расскажите, что нужно сделать.</p>
      </Card>
    )
  }, [applySessionState, error, isLoading, messages.length])

  return (
    <section className="page agent-page">
      {activeNote && (
        <Card className="agent-page__note">
          <div className="agent-page__note-header">
            <span className="agent-page__note-title">
              Работает с заметкой #{activeNote.id}
            </span>
            <button
              type="button"
              className="agent-page__note-button"
              onClick={() => navigate(`/notes/${activeNote.id}`)}
            >
              Открыть заметку
            </button>
          </div>
          {activeNote.summary && <p className="agent-page__note-summary">{activeNote.summary}</p>}
        </Card>
      )}

      <div className="agent-page__history">
        {conversation.map((message) => {
          const isUser = message.role === 'user'
          const isSystem = message.role === 'system'
          const AvatarIcon = isSystem ? IconInfoCircle : isUser ? IconUser : IconRobot
          return (
            <div
              key={message.id}
              className={clsx('agent-message', {
                'agent-message--outgoing': isUser,
                'agent-message--system': isSystem,
              })}
            >
              <div className="agent-message__avatar">
                <AvatarIcon size={18} />
              </div>
              <div className="agent-message__bubble">{renderMessageContent(message.content)}</div>
            </div>
          )
        })}
        {emptyState}
        <div ref={scrollAnchorRef} />
      </div>

      {uploadPhase !== 'idle' && (
        <div className="agent-progress">
          <span className="agent-progress__label">
            {uploadPhase === 'upload' ? 'Загружаем файл…' : 'Обрабатываем заметку…'}
          </span>
          <div className="agent-progress__track">
            {uploadPhase === 'upload' && typeof uploadProgress === 'number' ? (
              <div
                className="agent-progress__bar"
                style={{ width: `${Math.max(0, Math.min(1, uploadProgress)) * 100}%` }}
              />
            ) : (
              <div className="agent-progress__bar agent-progress__bar--indeterminate" />
            )}
          </div>
        </div>
      )}

      {error && messages.length > 0 && (
        <div className="agent-page__error">{error}</div>
      )}

      {suggestions.length > 0 && (
        <div className="agent-page__suggestions">
          <span className="agent-page__suggestions-label">Попробуйте:</span>
          <div className="agent-page__suggestions-list">
            {suggestions.map((item) => (
              <Chip key={item} onClick={() => handleSuggestion(item)}>
                {item}
              </Chip>
            ))}
          </div>
        </div>
      )}

      <div className="agent-page__composer-shell">
        <form className="agent-page__composer" onSubmit={handleSend}>
          <div className="agent-page__composer-row">
            <button
              type="button"
              className="agent-page__upload"
              onClick={triggerFileDialog}
              disabled={isSending || isUploading}
              aria-label="Загрузить файл"
            >
              <IconPaperclip size={18} stroke={2.2} />
            </button>
            <textarea
              ref={inputRef}
              className="agent-page__input"
              placeholder="Спросите про заметки или дайте команду агенту"
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              rows={3}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void handleSend()
                }
              }}
              disabled={isSending}
            />
          </div>
          <div className="agent-page__composer-actions">
            <button
              type="submit"
              className="ui-button agent-page__send"
              disabled={isSending || isUploading || !inputValue.trim()}
            >
              Отправить
              <IconSend size={18} stroke={2.2} />
            </button>
          </div>
          <input
            ref={fileInputRef}
            className="agent-page__file-input"
            type="file"
            accept="audio/*,video/*"
            onChange={handleFileChange}
          />
        </form>
      </div>
    </section>
  )
}
