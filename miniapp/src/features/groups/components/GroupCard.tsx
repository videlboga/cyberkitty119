import { IconEdit, IconTrash } from '@tabler/icons-react'
import clsx from 'clsx'
import type { Group } from '../types'

interface GroupCardProps {
  group: Group
  selected: boolean
  onSelect: (group: Group) => void
  onEdit: (group: Group) => void
  onDelete: (group: Group) => void
}

export const GroupCard = ({ group, selected, onSelect, onEdit, onDelete }: GroupCardProps) => (
  <div className={clsx('group-card', selected && 'group-card--selected')}>
    <button
      type="button"
      className="group-card__color"
      style={{ background: group.color ?? '#6366f1' }}
      onClick={() => onSelect(group)}
      aria-pressed={selected}
    />
    <div className="group-card__content" onClick={() => onSelect(group)}>
      <h3>{group.name}</h3>
      <p>{group.noteCount} заметок</p>
      <div className="group-card__tags">
        {group.tags.map((tag) => (
          <span key={tag}>#{tag}</span>
        ))}
      </div>
    </div>
    <div className="group-card__actions">
      <button type="button" onClick={() => onEdit(group)}>
        <IconEdit size={18} stroke={1.8} />
      </button>
      <button type="button" onClick={() => onDelete(group)}>
        <IconTrash size={18} stroke={1.8} />
      </button>
    </div>
  </div>
)
