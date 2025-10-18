import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const MIN_TIMEZONE_OFFSET = -12
export const MAX_TIMEZONE_OFFSET = 14

const clampTimezoneOffset = (value: number) =>
  Math.min(MAX_TIMEZONE_OFFSET, Math.max(MIN_TIMEZONE_OFFSET, value))

const deriveDefaultTimezone = () => {
  if (typeof Date === 'undefined') return 0
  const offsetInHours = -new Date().getTimezoneOffset() / 60
  return clampTimezoneOffset(Math.round(offsetInHours))
}

interface SettingsState {
  timezone: number
  betaMode: boolean
  betaInitialized: boolean
  setTimezone: (offset: number) => void
  setBetaMode: (enabled: boolean) => void
  resetBetaInitialization: () => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      timezone: deriveDefaultTimezone(),
      betaMode: false,
      betaInitialized: false,
      setTimezone: (offset) =>
        set(() => ({
          timezone: clampTimezoneOffset(Math.round(Number.isFinite(offset) ? offset : 0)),
        })),
      setBetaMode: (enabled) =>
        set(() => ({
          betaMode: Boolean(enabled),
          betaInitialized: true,
        })),
      resetBetaInitialization: () => set(() => ({ betaInitialized: false })),
    }),
    {
      name: 'miniapp-settings',
      version: 2,
      migrate: (persistedState) => {
        if (!persistedState) return persistedState
        return {
          ...persistedState,
          betaInitialized: Boolean((persistedState as Record<string, unknown>).betaInitialized ?? false),
        }
      },
      onRehydrateStorage: () => (state) => {
        state?.resetBetaInitialization?.()
      },
    },
  ),
)
