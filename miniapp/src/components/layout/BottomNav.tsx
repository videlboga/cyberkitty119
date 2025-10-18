import { IconListCheck, IconRobot, IconSettings, IconTags } from '@tabler/icons-react'
import clsx from 'clsx'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'

interface BottomNavProps {
  currentPath: string
}

const buildPath = (segment: string) => {
  if (segment === '/') {
    return '/'
  }
  const normalized = segment.replace(/^\//, '')
  return `/${normalized}`
}

const NAV_ITEMS = [
  { id: 'list', label: 'Список', path: buildPath('/'), icon: IconListCheck },
  { id: 'assistant', label: 'Агент', path: buildPath('assistant'), icon: IconRobot },
  { id: 'groups', label: 'Группы', path: buildPath('groups'), icon: IconTags },
  { id: 'settings', label: 'Настройки', path: buildPath('settings'), icon: IconSettings },
] as const

export const BottomNav = ({ currentPath: _currentPath }: BottomNavProps) => {
  const navigate = useNavigate()
  const currentPath = _currentPath || '/'

  const content = (
    <nav className="app-bottom-nav" aria-label="Основная навигация">
      {NAV_ITEMS.map(({ id, icon: Icon, path, label }) => {
        const isActive =
          path === '/'
            ? currentPath === '/'
            : currentPath === path || currentPath.startsWith(`${path}/`)

        return (
          <button
            key={id}
            type="button"
            className={clsx('app-bottom-nav__item', {
              'is-active': isActive,
              'app-bottom-nav__item--assistant': id === 'assistant',
            })}
            onClick={() => navigate(path)}
          >
            <Icon size={22} stroke={isActive ? 2.4 : 2} />
            <span>{label}</span>
          </button>
        )
      })}
    </nav>
  )

  if (typeof document === 'undefined') {
    return content
  }

  return createPortal(content, document.body)
}
