import { IconArrowLeft, IconCalendarEvent, IconHash, IconRobot, IconTags, IconTrash } from '@tabler/icons-react'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Card } from '@/components/common/Card'
import { Chip } from '@/components/common/Chip'
import { EmptyState } from '@/components/common/EmptyState'
import { useTelegram } from '@/app/hooks/useTelegram'
import { useTelegramHaptic } from '@/app/hooks/useTelegramHaptic'
import { useTelegramMainButton } from '@/app/hooks/useTelegramMainButton'
import { useCreateNoteMutation, useDeleteNoteMutation, useUpdateNoteMutation } from '@/features/notes/hooks/useNoteMutations'
import { useNoteQuery } from '@/features/notes/hooks/useNoteQuery'
import { useGroupsQuery } from '@/features/groups/hooks/useGroupsQuery'
import type { NoteType } from '@/features/notes/types'

interface NoteEditorPageProps {
  mode: 'create' | 'edit'
}

interface NoteFormState {
  title: string
  summary: string
  content: string
  tags: string[]
  groupIds: string[]
  type: NoteType
  status: string
  scheduledAt?: string
  color?: string
}

// const TYPE_OPTIONS: NoteType[] = ['task', 'meeting', 'idea', 'summary', 'reminder', 'note']
// const TYPE_LABELS: Record<NoteType, string> = {
//   task: 'Задача',
//   meeting: 'Созвон',
//   idea: 'Идея',
//   summary: 'Сводка',
//   reminder: 'Напоминание',
//   note: 'Заметка',
// }

const formatDatetimeLocal = (iso?: string) => {
  if (!iso) return ''
  try {
    const date = new Date(iso)
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}T${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  } catch (error) {
    console.warn('Failed to format date', iso, error)
    return ''
  }
}

export const NoteEditorPage = ({ mode }: NoteEditorPageProps) => {
  const navigate = useNavigate()
  const params = useParams<{ noteId: string }>()
  const noteId = params.noteId
  const { initData, webApp } = useTelegram()
  const { data: note, isLoading, isError } = useNoteQuery(mode === 'edit' ? noteId : undefined)
  const createMutation = useCreateNoteMutation()
  const updateMutation = useUpdateNoteMutation()
  const deleteMutation = useDeleteNoteMutation()
  const haptic = useTelegramHaptic()
  const isSaving = createMutation.isPending || updateMutation.isPending
  const { data: groups } = useGroupsQuery()

  const [formState, setFormState] = useState<NoteFormState>(() => ({
    title: '',
    summary: '',
    content: '',
    tags: [],
    groupIds: [],
    type: 'task',
    status: 'draft',
    scheduledAt: undefined,
    color: '#6366f1',
  }))
  const [tagInput, setTagInput] = useState('')

  useEffect(() => {
    if (note && mode === 'edit') {
      setFormState({
        title: note.title,
        summary: note.summary,
        content: note.content,
        tags: note.tags,
        groupIds: note.groupIds,
        type: note.type,
        status: note.status ?? 'draft',
        scheduledAt: note.scheduledAt ?? note.createdAt,
        color: note.color ?? '#6366f1',
      })
    }
  }, [note, mode])

  const handleTagSubmit = () => {
    if (!tagInput.trim()) return
    setFormState((prev) => ({
      ...prev,
      tags: Array.from(new Set([...prev.tags, tagInput.trim()])),
    }))
    setTagInput('')
  }

  const handleRemoveTag = (value: string) => {
    setFormState((prev) => ({
      ...prev,
      tags: prev.tags.filter((tag) => tag !== value),
    }))
  }

  const toggleGroup = (groupId: string) => {
    setFormState((prev) => {
      const exists = prev.groupIds.includes(groupId)
      return {
        ...prev,
        groupIds: exists ? prev.groupIds.filter((id) => id !== groupId) : [...prev.groupIds, groupId],
      }
    })
  }

  const goBack = useCallback(() => {
    if (typeof window !== 'undefined' && window.history.length > 1) {
      navigate(-1)
      return
    }
    navigate('/', { replace: true })
  }, [navigate])

  const handleSave = useCallback(async () => {
    const payload = {
      ...formState,
      status: formState.status ?? 'draft',
      scheduledAt: formState.scheduledAt || undefined,
    }

    try {
      if (mode === 'create') {
        await createMutation.mutateAsync(payload)
      } else if (noteId) {
        await updateMutation.mutateAsync({ id: noteId, data: payload })
      } else {
        return
      }
      haptic('medium')
      goBack()
    } catch (error) {
      console.error('Failed to save note', error)
      haptic('heavy')
      const message = error instanceof Error ? error.message : 'Неизвестная ошибка'
      window.alert(`Не удалось сохранить заметку: ${message}`)
    }
  }, [formState, mode, createMutation, updateMutation, noteId, haptic, goBack])

  const handleDelete = useCallback(async () => {
    if (!noteId) return
    const confirmed = window.confirm('Удалить заметку?')
    if (!confirmed) return
    await deleteMutation.mutateAsync(noteId)
    haptic('heavy')
    goBack()
  }, [noteId, deleteMutation, haptic, goBack])

  const openInAssistant = useCallback(() => {
    if (!noteId) return
    navigate(`/assistant?note=${noteId}`)
  }, [navigate, noteId])

  useTelegramMainButton({
    text: mode === 'create' ? 'Создать' : 'Сохранить',
    visible: Boolean(webApp),
    enabled: formState.title.trim().length > 0 && !isSaving,
    isLoading: isSaving,
    onClick: handleSave,
  })

  useEffect(() => {
    if (!webApp) return
    const backHandler = () => goBack()
    webApp.BackButton.show()
    webApp.BackButton.onClick(backHandler)
    return () => {
      webApp.BackButton.offClick(backHandler)
      webApp.BackButton.hide()
    }
  }, [webApp, goBack])

  if (mode === 'edit' && isLoading) {
    return <p className="note-editor__hint">Загружаем заметку...</p>
  }

  if (mode === 'edit' && isError) {
    return (
      <EmptyState
        title="Заметка не найдена"
        description="Возможно, она была удалена или вы получили устаревшую ссылку."
      />
    )
  }

  return (
    <form
      className="note-editor"
      onSubmit={(event) => {
        event.preventDefault()
        handleSave()
      }}
    >
      <div className="note-editor__topbar">
        <button
          type="button"
          className="ui-ghost-button note-editor__back"
          onClick={goBack}
        >
          <IconArrowLeft size={18} />
          Назад
        </button>
        <h2 className="note-editor__title">
          {mode === 'create' ? 'Новая заметка' : 'Редактирование заметки'}
        </h2>
      </div>

      <Card className="note-editor__section">
        <label className="note-editor__field">
          Заголовок
          <input
            type="text"
            placeholder="Название заметки"
            value={formState.title}
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, title: event.target.value }))
            }
            required
          />
        </label>
        <div className="note-editor__row">
          <label className="note-editor__field">
            Дата
            <input
              type="datetime-local"
              value={formatDatetimeLocal(formState.scheduledAt)}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, scheduledAt: event.target.value }))
              }
            />
          </label>
          {/* <label className="note-editor__field">
            Тип
            <select
              value={formState.type}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, type: event.target.value as NoteType }))
              }
            >
              {TYPE_OPTIONS.map((type) => (
                <option key={type} value={type}>
                  {TYPE_LABELS[type]}
                </option>
              ))}
            </select>
          </label> */}
        </div>
        {groups && groups.length > 0 && (
          <div className="note-editor__groups">
            <span className="note-editor__groups-label">
              <IconTags size={16} stroke={1.8} /> Группы
            </span>
            <div className="note-editor__groups-list">
              {groups.map((group) => (
                <Chip
                  key={group.id}
                  active={formState.groupIds.includes(group.id)}
                  onClick={() => toggleGroup(group.id)}
                  color={group.color ?? undefined}
                >
                  {group.name}
                </Chip>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card className="note-editor__section">
        <label className="note-editor__field">
          Краткое описание
          <textarea
            rows={3}
            placeholder="Короткий summary"
            value={formState.summary}
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, summary: event.target.value }))
            }
          />
        </label>
        <label className="note-editor__field">
          Полный текст
          <textarea
            rows={8}
            placeholder="Основной текст или Markdown"
            value={formState.content}
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, content: event.target.value }))
            }
          />
        </label>
      </Card>

      <Card className="note-editor__section">
        <div className="note-editor__tags">
          <label>
            <span>
              <IconHash size={16} stroke={1.8} /> Теги
            </span>
            <div className="note-editor__tag-input">
              <input
                type="text"
                placeholder="Добавить тег"
                value={tagInput}
                onChange={(event) => setTagInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ',') {
                    event.preventDefault()
                    handleTagSubmit()
                  }
                  if (event.key === 'Backspace' && !tagInput) {
                    const last = formState.tags.at(-1)
                    if (last) {
                      handleRemoveTag(last)
                    }
                  }
                }}
              />
              <button type="button" className="ui-button" onClick={handleTagSubmit}>
                Добавить
              </button>
            </div>
          </label>
          <div className="note-editor__tag-list">
            {formState.tags.map((tag) => (
              <Chip key={tag} active onClick={() => handleRemoveTag(tag)}>
                #{tag}
              </Chip>
            ))}
          </div>
        </div>
        {note?.attachments && note.attachments.length > 0 && (
          <div className="note-editor__attachments">
            <h4>Вложения</h4>
            <ul>
              {note.attachments.map((attachment) => (
                <li key={attachment.id}>
                  <span>{attachment.name}</span>
                  <span className="note-editor__attachment-type">{attachment.type}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <Card className="note-editor__section note-editor__meta">
        <div>
          <h4>
            <IconCalendarEvent size={16} stroke={1.8} /> Создано
          </h4>
          <p>
            {note?.createdAt
              ? format(new Date(note.createdAt), 'd MMMM yyyy, HH:mm', { locale: ru })
              : 'Будет создано при сохранении'}
          </p>
        </div>
        {mode === 'edit' && noteId && (
          <button type="button" className="note-editor__deeplink" onClick={openInAssistant}>
            <IconRobot size={16} stroke={1.8} /> Открыть в ИИ-агенте
          </button>
        )}
        {initData?.user && (
          <div className="note-editor__owner">
            Автор: {initData.user.first_name} {initData.user.last_name}
          </div>
        )}
      </Card>

      <footer className="note-editor__actions">
        <button type="submit" className="ui-button" disabled={createMutation.isPending || updateMutation.isPending}>
          {mode === 'create' ? 'Создать заметку' : 'Сохранить изменения'}
        </button>
        {mode === 'edit' && (
          <button
            type="button"
            className="ui-destructive-button"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            <IconTrash size={18} stroke={1.8} /> Удалить
          </button>
        )}
      </footer>
    </form>
  )
}
