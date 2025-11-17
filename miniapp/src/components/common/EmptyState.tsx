import type { ReactNode } from 'react'

interface EmptyStateProps {
  title: string
  description?: string
  icon?: ReactNode
  action?: ReactNode
}

export const EmptyState = ({ title, description, icon, action }: EmptyStateProps) => (
  <div className="ui-empty-state">
    {icon && <div className="ui-empty-state__icon">{icon}</div>}
    <h3>{title}</h3>
    {description && <p>{description}</p>}
    {action && <div className="ui-empty-state__action">{action}</div>}
  </div>
)
