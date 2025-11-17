import { IconPlus } from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'
import { Card } from '@/components/common/Card'
import { Chip } from '@/components/common/Chip'
import { EmptyState } from '@/components/common/EmptyState'
import { useTelegramHaptic } from '@/app/hooks/useTelegramHaptic'
import { GroupCard } from '@/features/groups/components/GroupCard'
import { useCreateGroupMutation, useDeleteGroupMutation, useMergeGroupMutation, useUpdateGroupMutation } from '@/features/groups/hooks/useGroupMutations'
import { useGroupSuggestionsQuery, useGroupsQuery } from '@/features/groups/hooks/useGroupsQuery'
import type { Group } from '@/features/groups/types'

interface GroupFormState {
  name: string
  color: string
  tags: string
}

const defaultFormState: GroupFormState = {
  name: '',
  color: '#6366f1',
  tags: '',
}

const tagsStringToArray = (tags: string) =>
  tags
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)

export const GroupsPage = () => {
  const { data: groups, isLoading } = useGroupsQuery()
  const { data: suggestions } = useGroupSuggestionsQuery()
  const createMutation = useCreateGroupMutation()
  const updateMutation = useUpdateGroupMutation()
  const deleteMutation = useDeleteGroupMutation()
  const mergeMutation = useMergeGroupMutation()
  const haptic = useTelegramHaptic()

  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingGroup, setEditingGroup] = useState<Group | null>(null)
  const [formState, setFormState] = useState<GroupFormState>(defaultFormState)
  const [mergeState, setMergeState] = useState<GroupFormState>({
    name: 'Новая группа',
    color: '#22d3ee',
    tags: '',
  })

  useEffect(() => {
    if (editingGroup) {
      setFormState({
        name: editingGroup.name,
        color: editingGroup.color ?? '#6366f1',
        tags: editingGroup.tags.join(', '),
      })
    }
  }, [editingGroup])

  const resetForm = () => {
    setFormState(defaultFormState)
    setEditingGroup(null)
    setIsCreateOpen(false)
  }

  const handleSubmit = async () => {
    if (!formState.name) return
    const payload = {
      name: formState.name,
      color: formState.color,
      tags: tagsStringToArray(formState.tags),
    }

    if (editingGroup) {
      await updateMutation.mutateAsync({ id: editingGroup.id, data: payload })
    } else {
      await createMutation.mutateAsync(payload)
    }
    haptic('medium')
    resetForm()
  }

  const handleDelete = async (group: Group) => {
    const confirmed = window.confirm(`Удалить группу «${group.name}»?`)
    if (!confirmed) return
    await deleteMutation.mutateAsync(group.id)
    haptic('heavy')
    setSelectedIds((prev) => prev.filter((id) => id !== group.id))
  }

  const toggleSelect = (group: Group) => {
    setSelectedIds((prev) =>
      prev.includes(group.id) ? prev.filter((id) => id !== group.id) : [...prev, group.id],
    )
  }

  const selectedGroups = useMemo(
    () => groups?.filter((group) => selectedIds.includes(group.id)) ?? [],
    [groups, selectedIds],
  )

  const handleMerge = async () => {
    if (selectedIds.length < 2) return
    await mergeMutation.mutateAsync({
      ids: selectedIds,
      name: mergeState.name,
      color: mergeState.color,
    })
    haptic('medium')
    setSelectedIds([])
  }

  return (
    <section className="page groups-page">
      <Card className="groups-page__header" padding="sm">
        <div>
          <h2>Управление группами</h2>
          <p>Объединяйте теги, чтобы быстрее ориентироваться в заметках.</p>
        </div>
        <button
          type="button"
          className="ui-button"
          onClick={() => {
            resetForm()
            setIsCreateOpen(true)
          }}
        >
          <IconPlus size={18} stroke={2} /> Новая группа
        </button>
      </Card>

      {isCreateOpen && (
        <Card className="group-form">
          <header>
            <h3>Создать группу</h3>
          </header>
          <div className="group-form__grid">
            <label>
              Название
              <input
                type="text"
                value={formState.name}
                onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
              />
            </label>
            <label>
              Цвет
              <input
                type="color"
                value={formState.color}
                onChange={(event) => setFormState((prev) => ({ ...prev, color: event.target.value }))}
              />
            </label>
            <label>
              Теги через запятую
              <input
                type="text"
                value={formState.tags}
                onChange={(event) => setFormState((prev) => ({ ...prev, tags: event.target.value }))}
              />
            </label>
          </div>
          <footer className="group-form__footer">
            <button type="button" className="ui-button" onClick={handleSubmit}>
              Сохранить
            </button>
            <button type="button" className="ui-ghost-button" onClick={resetForm}>
              Отмена
            </button>
          </footer>
        </Card>
      )}

      {editingGroup && !isCreateOpen && (
        <Card className="group-form">
          <header>
            <h3>Редактирование: {editingGroup.name}</h3>
          </header>
          <div className="group-form__grid">
            <label>
              Название
              <input
                type="text"
                value={formState.name}
                onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
              />
            </label>
            <label>
              Цвет
              <input
                type="color"
                value={formState.color}
                onChange={(event) => setFormState((prev) => ({ ...prev, color: event.target.value }))}
              />
            </label>
            <label>
              Теги через запятую
              <input
                type="text"
                value={formState.tags}
                onChange={(event) => setFormState((prev) => ({ ...prev, tags: event.target.value }))}
              />
            </label>
          </div>
          <footer className="group-form__footer">
            <button type="button" className="ui-button" onClick={handleSubmit}>
              Обновить
            </button>
            <button type="button" className="ui-ghost-button" onClick={resetForm}>
              Отмена
            </button>
          </footer>
        </Card>
      )}

      {isLoading && <p className="groups-page__hint">Загружаем группы...</p>}

      {!isLoading && groups && groups.length > 0 && (
        <div className="groups-page__list">
          {groups.map((group) => (
            <GroupCard
              key={group.id}
              group={group}
              selected={selectedIds.includes(group.id)}
              onSelect={toggleSelect}
              onEdit={(item) => {
                setIsCreateOpen(false)
                setEditingGroup(item)
              }}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {!isLoading && groups && groups.length === 0 && (
        <EmptyState
          title="Групп нет"
          description="Создайте первую группу, чтобы организовать заметки по тегам."
        />
      )}

      {selectedGroups.length >= 2 && (
        <Card className="group-form">
          <header>
            <h3>Объединить выбранные группы</h3>
            <p>
              Выбрано: {selectedGroups.length} —{' '}
              {selectedGroups.map((group) => group.name).join(', ')}
            </p>
          </header>
          <div className="group-form__grid">
            <label>
              Название новой группы
              <input
                type="text"
                value={mergeState.name}
                onChange={(event) => setMergeState((prev) => ({ ...prev, name: event.target.value }))}
              />
            </label>
            <label>
              Цвет
              <input
                type="color"
                value={mergeState.color}
                onChange={(event) => setMergeState((prev) => ({ ...prev, color: event.target.value }))}
              />
            </label>
          </div>
          <footer className="group-form__footer">
            <button type="button" className="ui-button" onClick={handleMerge}>
              Объединить
            </button>
            <button type="button" className="ui-ghost-button" onClick={() => setSelectedIds([])}>
              Сбросить выбор
            </button>
          </footer>
        </Card>
      )}

      {suggestions && suggestions.length > 0 && (
        <Card className="group-suggestions">
          <header>
            <h3>AI-предложения</h3>
            <p>Мы подобрали потенциальные группы на основе свежих заметок.</p>
          </header>
          <div className="group-suggestions__list">
            {suggestions.map((suggestion) => (
              <div key={suggestion.id} className="suggestion-item">
                <div>
                  <h4>{suggestion.name}</h4>
                  <p>Возможные теги:</p>
                  <div className="suggestion-item__tags">
                    {suggestion.tags.map((tag) => (
                      <Chip key={tag}>#{tag}</Chip>
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  className="ui-button"
                  onClick={async () => {
                    await createMutation.mutateAsync({
                      name: suggestion.name,
                      color: '#38bdf8',
                      tags: suggestion.tags,
                    })
                    haptic('medium')
                  }}
                >
                  Добавить
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </section>
  )
}
