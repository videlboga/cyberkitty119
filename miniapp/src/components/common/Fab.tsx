import type { ButtonHTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'

interface FabProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: ReactNode
}

export const Fab = ({ icon, className, children, ...rest }: FabProps) => (
  <button type="button" className={clsx('ui-fab', className)} {...rest}>
    {icon && <span className="ui-fab__icon">{icon}</span>}
    {children && <span className="ui-fab__label">{children}</span>}
  </button>
)
