import { IconPlus, IconRobot } from '@tabler/icons-react'
import { useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/common/Card'
import { EmptyState } from '@/components/common/EmptyState'
import { Fab } from '@/components/common/Fab'
import { FilterBar } from '@/features/filters/components/FilterBar'
import { NoteCard } from '@/features/notes/components/NoteCard'
import { useNotesQuery } from '@/features/notes/hooks/useNotesQuery'
import { useGroupsQuery } from '@/features/groups/hooks/useGroupsQuery'
import type { Group } from '@/features/groups/types'

export const NotesListPage = () => {
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useNotesQuery()
  const { data: groups } = useGroupsQuery()

  const openAgent = useCallback(() => {
    navigate('/assistant')
  }, [navigate])

  const availableTags = useMemo(
    () => data?.items.flatMap((note) => note.tags) ?? [],
    [data?.items],
  )

  const groupMap = useMemo(() => {
    const map = new Map<string, Group>()
    groups?.forEach((group) => {
      map.set(group.id, group)
    })
    return map
  }, [groups])

  return (
    <section className="page notes-page">
      <FilterBar availableTags={availableTags} groups={groups ?? []} />

      <Card className="notes-page__agent-shortcut">
        <div>
          <h3>
            <IconRobot size={18} stroke={1.8} /> ИИ-агент
          </h3>
          <p>Диалог с ассистентом и мгновенный поиск по заметкам.</p>
        </div>
        <button type="button" className="ui-button" onClick={openAgent}>
          Открыть
        </button>
      </Card>

      {isLoading && (
        <div className="notes-page__grid">
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={index} className="skeleton-card" />
          ))}
        </div>
      )}

      {isError && (
        <EmptyState
          title="Не удалось загрузить заметки"
          description="Проверьте подключение и повторите попытку."
          action={
            <button type="button" className="ui-button" onClick={() => refetch()}>
              Повторить
            </button>
          }
        />
      )}

      {!isLoading && !isError && data && data.items.length > 0 && (
        <div className="notes-page__grid">
          {data.items.map((note) => (
            <NoteCard key={note.id} note={note} groupMap={groupMap} />
          ))}
        </div>
      )}

      {!isLoading && !isError && data && data.items.length === 0 && (
        <EmptyState
          title="Заметки не найдены"
          description="Попробуйте изменить фильтры или создайте новую запись."
        />
      )}

      <Fab icon={<IconPlus size={20} stroke={2.4} />} onClick={() => navigate('/notes/new')}>
        Создать
      </Fab>
    </section>
  )
}
