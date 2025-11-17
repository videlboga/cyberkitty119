import { IconArrowRight, IconCalendarEvent, IconTag, IconTags } from '@tabler/icons-react'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { useEffect, useState, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/common/Card'
import { Chip } from '@/components/common/Chip'
import type { Group } from '@/features/groups/types'
import type { Note } from '../types'
// import type { NoteType } from '../types'

// const TYPE_LABELS: Record<NoteType, string> = {
//   task: 'Задача',
//   meeting: 'Созвон',
//   idea: 'Идея',
//   summary: 'Сводка',
//   reminder: 'Напоминание',
//   note: 'Заметка',
// }

const VISIBLE_TAG_COUNT = 10

interface NoteCardProps {
  note: Note
  groupMap?: Map<string, Group>
}

const formatDate = (value?: string) => {
  if (!value) return null
  try {
    return format(new Date(value), 'd MMM, HH:mm', { locale: ru })
  } catch (error) {
    console.warn('Failed to format date', value, error)
    return null
  }
}

export const NoteCard = ({ note, groupMap }: NoteCardProps) => {
  const navigate = useNavigate()
  const [showAllTags, setShowAllTags] = useState(false)

  useEffect(() => {
    setShowAllTags(false)
  }, [note.id])

  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    navigate(`/notes/${note.id}`)
  }

  const dateLabel = formatDate(note.scheduledAt ?? note.createdAt)
  const groups = note.groupIds
    .map((id) => groupMap?.get(id))
    .filter((group): group is Group => Boolean(group))
  const hasHiddenTags = note.tags.length > VISIBLE_TAG_COUNT
  const displayedTags = showAllTags ? note.tags : note.tags.slice(0, VISIBLE_TAG_COUNT)

  return (
    <Card className="note-card" interactive onClick={handleClick}>
      <div className="note-card__header">
        <div>
          <h3>{note.title}</h3>
          {dateLabel && (
            <span className="note-card__date">
              <IconCalendarEvent size={16} stroke={1.8} />
              {dateLabel}
            </span>
          )}
        </div>
      </div>
      {groups.length > 0 && (
        <div className="note-card__groups">
          {groups.map((group) => (
            <Chip key={group.id} color={group.color ?? undefined} leadingIcon={<IconTags size={14} stroke={1.8} />}>
              {group.name}
            </Chip>
          ))}
        </div>
      )}
      <p className="note-card__summary">{note.summary}</p>
      {note.tags.length > 0 && (
        <>
          <div className="note-card__tags">
            {displayedTags.map((tag) => (
              <Chip key={tag} leadingIcon={<IconTag size={14} stroke={1.8} />}>
                {tag}
              </Chip>
            ))}
          </div>
          {hasHiddenTags && (
            <Chip
              className="note-card__tags-toggle"
              onClick={(event) => {
                event.stopPropagation()
                setShowAllTags((prev) => !prev)
              }}
            >
              {showAllTags ? 'Свернуть' : 'Развернуть'}
            </Chip>
          )}
        </>
      )}
      <footer className="note-card__footer">
        {/* <span className="note-card__type">{TYPE_LABELS[note.type] ?? 'Заметка'}</span> */}
        <IconArrowRight size={18} stroke={2} />
      </footer>
    </Card>
  )
}
