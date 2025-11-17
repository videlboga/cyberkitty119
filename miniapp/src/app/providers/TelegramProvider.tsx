import type { PropsWithChildren } from 'react'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ThemeParams, WebApp, WebAppInitData } from '@twa-dev/types'

interface TelegramContextValue {
  webApp?: WebApp
  initData?: WebAppInitData
  initDataRaw?: string
  themeParams?: ThemeParams
  colorScheme: 'light' | 'dark'
  isReady: boolean
}

const prefersDark = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-color-scheme: dark)').matches

const BASE_COLORS = {
  light: {
    '--tg-theme-bg-color': '#ffffff',
    '--tg-theme-secondary-bg-color': '#f5f7fb',
    '--tg-theme-surface-color': '#ffffff',
    '--tg-theme-text-color': '#0f172a',
    '--tg-theme-hint-color': '#64748b',
    '--tg-theme-link-color': '#3b82f6',
    '--tg-theme-button-color': '#3b82f6',
    '--tg-theme-button-text-color': '#ffffff',
    '--tg-theme-accent-color': '#0ea5e9',
  },
  dark: {
    '--tg-theme-bg-color': '#040712',
    '--tg-theme-secondary-bg-color': '#0f172a',
    '--tg-theme-surface-color': '#111827',
    '--tg-theme-text-color': '#f8fafc',
    '--tg-theme-hint-color': '#94a3b8',
    '--tg-theme-link-color': '#3b82f6',
    '--tg-theme-button-color': '#3b82f6',
    '--tg-theme-button-text-color': '#ffffff',
    '--tg-theme-accent-color': '#22d3ee',
  },
} as const

const TelegramContext = createContext<TelegramContextValue>({
  colorScheme: prefersDark() ? 'dark' : 'light',
  isReady: false,
  initDataRaw: undefined,
})

const themeParamMap: Partial<Record<keyof ThemeParams, string>> = {
  bg_color: '--tg-theme-bg-color',
  secondary_bg_color: '--tg-theme-secondary-bg-color',
  text_color: '--tg-theme-text-color',
  hint_color: '--tg-theme-hint-color',
  link_color: '--tg-theme-link-color',
  button_color: '--tg-theme-button-color',
  button_text_color: '--tg-theme-button-text-color',
}

type ThemeKeys = keyof typeof themeParamMap

const applyTheme = (
  mode: 'light' | 'dark',
  themeParams?: ThemeParams,
) => {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const fallback = BASE_COLORS[mode]
  Object.entries(fallback).forEach(([key, value]) => {
    root.style.setProperty(key, value)
  })
  root.dataset.colorScheme = mode

  if (!themeParams) return

  ;(Object.entries(themeParamMap) as Array<[ThemeKeys, string]>).forEach(
    ([key, variableName]) => {
      const value = themeParams[key]
      if (value) {
        root.style.setProperty(variableName, value)
      }
    },
  )
}

const deriveColorScheme = (
  webApp?: WebApp,
  themeParams?: ThemeParams,
): 'light' | 'dark' => {
  if (webApp?.colorScheme === 'light' || webApp?.colorScheme === 'dark') {
    return webApp.colorScheme
  }
  if (themeParams?.bg_color) {
    return isColorDark(themeParams.bg_color) ? 'dark' : 'light'
  }
  return prefersDark() ? 'dark' : 'light'
}

const isColorDark = (color: string) => {
  const hex = color.startsWith('#') ? color.slice(1) : color
  if (hex.length !== 6) return false
  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
  return luminance < 0.5
}

export const TelegramProvider = ({ children }: PropsWithChildren) => {
  const initialMode = prefersDark() ? 'dark' : 'light'
  const [contextValue, setContextValue] = useState<TelegramContextValue>({
    colorScheme: initialMode,
    isReady: false,
    initDataRaw: undefined,
  })

  useEffect(() => {
    let cleanup: (() => void) | undefined
    let timeoutId: number | undefined
    let attempts = 0
    const MAX_ATTEMPTS = 50

    const bootstrap = () => {
      const tg = window.Telegram?.WebApp
      if (!tg) {
        if (attempts >= MAX_ATTEMPTS) {
          applyTheme(initialMode)
          setContextValue((prev) => ({ ...prev, isReady: true, initDataRaw: undefined, colorScheme: initialMode }))
          return
        }
        attempts += 1
        timeoutId = window.setTimeout(bootstrap, 100)
        return
      }

      const handleUpdate = () => {
        const themeParams = tg.themeParams
        const colorScheme = deriveColorScheme(tg, themeParams)
        applyTheme(colorScheme, themeParams)
        document.documentElement.dataset.colorScheme = colorScheme
        setContextValue({
          webApp: tg,
          initData: tg.initDataUnsafe,
          initDataRaw: tg.initData || undefined,
          themeParams,
          colorScheme,
          isReady: true,
        })
      }

      tg.ready()
      tg.expand()
      handleUpdate()
      const themeListener = () => handleUpdate()
      tg.onEvent('themeChanged', themeListener)

      cleanup = () => {
        tg.offEvent('themeChanged', themeListener)
      }
    }

    bootstrap()

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
      cleanup?.()
    }
  }, [])

  const value = useMemo(() => contextValue, [contextValue])

  return <TelegramContext.Provider value={value}>{children}</TelegramContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useTelegramContext = () => {
  const context = useContext(TelegramContext)
  if (!context) {
    throw new Error('useTelegramContext must be used within TelegramProvider')
  }
  return context
}
