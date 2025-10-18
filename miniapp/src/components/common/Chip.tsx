import clsx from 'clsx'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean
  leadingIcon?: ReactNode
  color?: string
}

export const Chip = ({
  active,
  leadingIcon,
  color,
  className,
  children,
  ...rest
}: ChipProps) => (
  <button
    type="button"
    className={clsx('ui-chip', active && 'ui-chip--active', className)}
    style={color ? { '--chip-color': color } as React.CSSProperties : undefined}
    {...rest}
  >
    {leadingIcon && <span className="ui-chip__icon">{leadingIcon}</span>}
    <span>{children}</span>
  </button>
)
