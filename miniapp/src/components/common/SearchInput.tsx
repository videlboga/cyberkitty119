import { IconSearch } from '@tabler/icons-react'
import type { InputHTMLAttributes } from 'react'
import clsx from 'clsx'

interface SearchInputProps extends InputHTMLAttributes<HTMLInputElement> {
  onClear?: () => void
}

export const SearchInput = ({ className, onClear, value, ...rest }: SearchInputProps) => (
  <div className={clsx('ui-search-input', className)}>
    <IconSearch size={18} stroke={1.8} />
    <input type="search" value={value} {...rest} />
    {value && value.toString().length > 0 && (
      <button type="button" className="ui-search-input__clear" onClick={onClear}>
        ×
      </button>
    )}
  </div>
)
