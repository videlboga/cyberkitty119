import clsx from 'clsx'
import type { HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: 'sm' | 'md' | 'lg'
  interactive?: boolean
}

export const Card = ({
  padding = 'md',
  interactive,
  className,
  children,
  ...rest
}: CardProps) => (
  <div
    className={clsx(
      'ui-card',
      `ui-card--${padding}`,
      interactive && 'ui-card--interactive',
      className,
    )}
    {...rest}
  >
    {children}
  </div>
)
