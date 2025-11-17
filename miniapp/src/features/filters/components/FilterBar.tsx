import { IconCalendarTime, IconTag, IconTags } from '@tabler/icons-react'
// import { IconAdjustments } from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'
import { Chip } from '@/components/common/Chip'
import { SearchInput } from '@/components/common/SearchInput'
import type { SegmentedOption } from '@/components/common/SegmentedControl'
import { SegmentedControl } from '@/components/common/SegmentedControl'
import type { Group } from '@/features/groups/types'
import type { Period } from '../store/useNoteFilters'
import { useNoteFilters } from '../store/useNoteFilters'

interface FilterBarProps {
  availableTags: string[]
  groups: Group[]
}

const PERIOD_OPTIONS: SegmentedOption<Period>[] = [
  { value: 'today', label: 'Сегодня' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'custom', label: 'Диапазон' },
]

// const TYPE_OPTIONS = [
//   { value: 'all', label: 'Все' },
//   { value: 'task', label: 'Задачи' },
//   { value: 'meeting', label: 'Созвоны' },
//   { value: 'idea', label: 'Идеи' },
//   { value: 'summary', label: 'Сводки' },
//   { value: 'note', label: 'Заметки' },
//   { value: 'reminder', label: 'Напоминания' },
// ] as const

const VISIBLE_TAGS_COUNT = 10

export const FilterBar = ({ availableTags, groups }: FilterBarProps) => {
  const {
    period,
    setPeriod,
    dateFrom,
    dateTo,
    setDateRange,
    groupId,
    setGroupId,
    // type,
    // setType,
    tags,
    toggleTag,
    search,
    setSearch,
  } = useNoteFilters()

  const [searchValue, setSearchValue] = useState(search)
  const [showAllTags, setShowAllTags] = useState(false)

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearch(searchValue)
    }, 250)

    return () => window.clearTimeout(timeout)
  }, [searchValue, setSearch])

  useEffect(() => {
    setSearchValue(search)
  }, [search])

  const tagOptions = useMemo(() => {
    if (!availableTags.length) return []
    const unique = Array.from(new Set(availableTags))
    return unique.sort((a, b) => a.localeCompare(b))
  }, [availableTags])

  const groupOptions = useMemo(() => {
    if (!groups.length) return []
    return [...groups].sort((a, b) => a.name.localeCompare(b.name))
  }, [groups])

  useEffect(() => {
    setShowAllTags(false)
  }, [tagOptions])

  const hasHiddenTags = tagOptions.length > VISIBLE_TAGS_COUNT
  const displayedTags = showAllTags ? tagOptions : tagOptions.slice(0, VISIBLE_TAGS_COUNT)

  return (
    <section className="filter-bar">
      <div className="filter-bar__section">
        <div className="filter-bar__label">
          <IconCalendarTime size={18} stroke={1.8} />
          Период
        </div>
        <SegmentedControl
          size="sm"
          value={period}
          onChange={(value) => setPeriod(value)}
          options={PERIOD_OPTIONS}
        />
      </div>
      {period === 'custom' && (
        <div className="filter-bar__section filter-bar__section--grid">
          <div className="filter-bar__label">
            <IconCalendarTime size={18} stroke={1.8} /> Диапазон дат
          </div>
          <div className="filter-bar__date-range">
            <label>
              с
              <input
                type="date"
                value={dateFrom ?? ''}
                onChange={(event) =>
                  setDateRange(event.target.value || undefined, dateTo)
                }
              />
            </label>
            <label>
              по
              <input
                type="date"
                value={dateTo ?? ''}
                onChange={(event) =>
                  setDateRange(dateFrom, event.target.value || undefined)
                }
              />
            </label>
          </div>
        </div>
      )}
      <div className="filter-bar__section">
        <SearchInput
          placeholder="Поиск по заметкам"
          value={searchValue}
          onChange={(event) => setSearchValue(event.target.value)}
          onClear={() => setSearchValue('')}
        />
      </div>
      {groupOptions.length > 0 && (
        <div className="filter-bar__section filter-bar__section--grid">
          <div className="filter-bar__label">
            <IconTags size={18} stroke={1.8} /> Группы
          </div>
          <div className="filter-bar__chips">
            <Chip active={groupId === 'all'} onClick={() => setGroupId('all')}>
              Все
            </Chip>
            {groupOptions.map((group) => (
              <Chip
                key={group.id}
                active={groupId === group.id}
                onClick={() => setGroupId(groupId === group.id ? 'all' : group.id)}
                color={group.color ?? undefined}
              >
                {group.name}
              </Chip>
            ))}
          </div>
        </div>
      )}
      {/* <div className="filter-bar__section filter-bar__section--grid">
        <div className="filter-bar__label">
          <IconAdjustments size={18} stroke={1.8} />
          Тип
        </div>
        <div className="filter-bar__chips">
          {TYPE_OPTIONS.map((option) => (
            <Chip
              key={option.value}
              active={type === option.value}
              onClick={() => setType(option.value as typeof type)}
            >
              {option.label}
            </Chip>
          ))}
        </div>
      </div> */}
      {tagOptions.length > 0 && (
        <div className="filter-bar__section filter-bar__section--grid">
          <div className="filter-bar__label">
            <IconTag size={18} stroke={1.8} /> Теги
          </div>
          <div className="filter-bar__chips">
            {displayedTags.map((tag) => (
              <Chip key={tag} active={tags.includes(tag)} onClick={() => toggleTag(tag)}>
                {tag}
              </Chip>
            ))}
            {hasHiddenTags && (
              <Chip onClick={() => setShowAllTags((prev) => !prev)}>
                {showAllTags ? 'Свернуть' : `Развернуть +${tagOptions.length - VISIBLE_TAGS_COUNT}`}
              </Chip>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
