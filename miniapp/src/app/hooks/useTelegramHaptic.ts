import { useCallback } from 'react'
import { useTelegram } from './useTelegram'

export const useTelegramHaptic = () => {
  const { webApp } = useTelegram()

  return useCallback(
    (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft' = 'light') => {
      try {
        webApp?.HapticFeedback.impactOccurred(style)
      } catch (error) {
        console.warn('Haptic feedback is not available', error)
      }
    },
    [webApp],
  )
}
