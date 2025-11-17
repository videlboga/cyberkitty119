import clsx from 'clsx'
import type { ReactNode } from 'react'

export interface SegmentedOption<T extends string> {
  value: T
  label: string
  icon?: ReactNode
}

interface SegmentedControlProps<T extends string> {
  value: T
  onChange: (value: T) => void
  options: ReadonlyArray<SegmentedOption<T>>
  className?: string
  size?: 'sm' | 'md'
}

export const SegmentedControl = <T extends string>({
  value,
  onChange,
  options,
  className,
  size = 'md',
}: SegmentedControlProps<T>) => (
  <div className={clsx('ui-segmented', `ui-segmented--${size}`, className)}>
    {options.map((option) => {
      const isActive = option.value === value
      return (
        <button
          key={option.value}
          type="button"
          className={clsx('ui-segmented__item', isActive && 'is-active')}
          onClick={() => onChange(option.value)}
        >
          {option.icon && <span className="ui-segmented__icon">{option.icon}</span>}
          <span>{option.label}</span>
        </button>
      )
    })}
  </div>
)
