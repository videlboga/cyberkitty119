import { IconCalendar, IconCalendarEvent, IconClock } from '@tabler/icons-react'
import { format, isSameDay, isSameWeek, isSameMonth } from 'date-fns'
import { ru } from 'date-fns/locale'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/common/Card'
import { Chip } from '@/components/common/Chip'
import { EmptyState } from '@/components/common/EmptyState'
import { SegmentedControl } from '@/components/common/SegmentedControl'
import { FilterBar } from '@/features/filters/components/FilterBar'
import { useNotesQuery } from '@/features/notes/hooks/useNotesQuery'
import type { Note } from '@/features/notes/types'

const calendarViews = [
  { value: 'day', label: 'День' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
] as const

type CalendarView = (typeof calendarViews)[number]['value']

type CalendarGroup = {
  date: string
  notes: Note[]
}

const groupNotesByDate = (notes: Note[], view: CalendarView) => {
  const groups: CalendarGroup[] = []

  notes.forEach((note) => {
    if (!note.scheduledAt) return
    const date = new Date(note.scheduledAt)
    const existingGroup = groups.find((group) => {
      const groupDate = new Date(group.date)
      if (view === 'day') return isSameDay(groupDate, date)
      if (view === 'week') return isSameWeek(groupDate, date, { weekStartsOn: 1 })
      return isSameMonth(groupDate, date)
    })

    if (existingGroup) {
      existingGroup.notes.push(note)
    } else {
      groups.push({ date: note.scheduledAt, notes: [note] })
    }
  })

  return groups.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
}

const getDateLabel = (value: string, view: CalendarView) => {
  const date = new Date(value)
  switch (view) {
    case 'day':
      return format(date, 'd MMMM, EEEE', { locale: ru })
    case 'week':
      return `Неделя ${format(date, 'w', { locale: ru })}`
    case 'month':
    default:
      return format(date, 'LLLL yyyy', { locale: ru })
  }
}

export const CalendarPage = () => {
  const { data, isLoading } = useNotesQuery()
  const [view, setView] = useState<CalendarView>('week')
  const navigate = useNavigate()

  const availableTags = useMemo(
    () => data?.items.flatMap((note) => note.tags) ?? [],
    [data?.items],
  )

  const events = useMemo(
    () => data?.items.filter((note) => Boolean(note.scheduledAt)) ?? [],
    [data?.items],
  )

  const groups = useMemo(() => groupNotesByDate(events, view), [events, view])

  return (
    <section className="page calendar-page">
      <FilterBar availableTags={availableTags} groups={[]} />

      <Card className="calendar-page__toolbar" padding="sm">
        <div className="toolbar__title">
          <IconCalendar size={18} stroke={1.8} />
          Представление
        </div>
        <SegmentedControl value={view} onChange={setView} options={calendarViews} size="sm" />
      </Card>

      {isLoading && <p className="calendar-page__hint">Загружаем события...</p>}

      {!isLoading && groups.length === 0 && (
        <EmptyState
          title="Событий не найдено"
          description="Запланируйте заметки или измените фильтры."
          icon={<IconCalendarEvent size={42} stroke={1.6} />}
        />
      )}

      {!isLoading && groups.length > 0 && (
        <div className="calendar-page__agenda">
          {groups.map((group) => (
            <div key={group.date} className="calendar-group">
              <header className="calendar-group__header">
                <h3>{getDateLabel(group.date, view)}</h3>
                <span>{group.notes.length} событие(й)</span>
              </header>
              <div className="calendar-group__notes">
                {group.notes.map((note) => (
                  <Card
                    key={note.id}
                    padding="sm"
                    className="calendar-note"
                    interactive
                    onClick={() => navigate(`/notes/${note.id}`)}
                  >
                    <div className="calendar-note__time">
                      <IconClock size={16} stroke={1.8} />
                      {format(new Date(note.scheduledAt ?? note.createdAt), 'HH:mm', {
                        locale: ru,
                      })}
                    </div>
                    <div className="calendar-note__details">
                      <h4>{note.title}</h4>
                      <p>{note.summary}</p>
                      <div className="calendar-note__tags">
                        <Chip>{note.type}</Chip>
                        {note.tags.slice(0, 3).map((tag) => (
                          <Chip key={tag}>{tag}</Chip>
                        ))}
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
