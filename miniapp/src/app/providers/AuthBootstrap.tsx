import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTelegram } from '@/app/hooks/useTelegram'
import { apiClient } from '@/lib/api-client'
import { useAuthStore } from '@/store/authStore'
import { useSettingsStore } from '@/store/settingsStore'

const AUTH_STORAGE_KEY = 'miniapp-token'
const USER_STORAGE_KEY = 'miniapp-user'
const REFERRAL_STORAGE_KEY = 'miniapp-referral-code'

export const AuthBootstrap = () => {
  const { initDataRaw, isReady } = useTelegram()
  const queryClient = useQueryClient()
  const setAuthError = useAuthStore((state) => state.setError)
  const updateDebugInfo = useAuthStore((state) => state.setDebugInfo)
  const setShowDebug = useAuthStore((state) => state.setShowDebug)
  const [attempted, setAttempted] = useState(false)
  const [retryCount, setRetryCount] = useState(0)
  const [localDebugInfo, setLocalDebugInfo] = useState<{
    initDataRaw?: string
    webAppInitData?: string
    initDataUnsafe?: string
  }>()
  const maxRetries = 50
  const retryDelayMs = 120
  const inflightRef = useRef(false)

  useEffect(() => {
    if (!isReady) return
    if (attempted || inflightRef.current) return

    let resolvedInitData = initDataRaw?.trim() || ''
    let webAppInitData = ''
    let unsafeInitData = ''
    let referralCode: string | undefined
    let utmSource: string | undefined
    let utmMedium: string | undefined
    let utmCampaign: string | undefined

    if (!resolvedInitData && typeof window !== 'undefined') {
      const telegramInitData = window.Telegram?.WebApp?.initData
      if (telegramInitData && telegramInitData.trim()) {
        resolvedInitData = telegramInitData.trim()
        webAppInitData = telegramInitData
      } else if (telegramInitData) {
        webAppInitData = telegramInitData
      }
    }

    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search)
      const fromQuery = params.get('tgWebAppData')
      if (!resolvedInitData && fromQuery && fromQuery.trim()) {
        resolvedInitData = fromQuery.trim()
      }

      const refFromQuery = params.get('ref')?.trim()
      if (refFromQuery) {
        referralCode = refFromQuery
        window.localStorage.setItem(REFERRAL_STORAGE_KEY, refFromQuery)
      } else {
        const storedReferral = window.localStorage.getItem(REFERRAL_STORAGE_KEY)?.trim()
        if (storedReferral) {
          referralCode = storedReferral
        }
      }

      utmSource = params.get('utm_source')?.trim() || undefined
      utmMedium = params.get('utm_medium')?.trim() || undefined
      utmCampaign = params.get('utm_campaign')?.trim() || undefined
    }

    if (!resolvedInitData && typeof window !== 'undefined') {
      const unsafe = window.Telegram?.WebApp?.initDataUnsafe
      if (unsafe && typeof unsafe === 'object') {
        const entries = Object.entries(unsafe).filter(
          ([, value]) => value !== undefined && value !== null,
        )
        if (entries.length > 0) {
          const normalized = new URLSearchParams()
          for (const [key, value] of entries) {
            if (typeof value === 'object') {
              normalized.append(key, JSON.stringify(value))
            } else {
              normalized.append(key, String(value))
            }
          }
          const candidate = normalized.toString()
          if (candidate.trim()) {
            resolvedInitData = candidate
          }
        }
        unsafeInitData = JSON.stringify(unsafe)
      }
    }

    const debugPayload = {
      initDataRaw: initDataRaw || undefined,
      webAppInitData: webAppInitData || undefined,
      initDataUnsafe: unsafeInitData || undefined,
    }
    updateDebugInfo(debugPayload)
    setLocalDebugInfo(debugPayload)

    if (!resolvedInitData) {
      if (retryCount < maxRetries) {
        const timer = window.setTimeout(() => {
          setRetryCount((current) => current + 1)
        }, retryDelayMs)
        return () => window.clearTimeout(timer)
      }

      console.warn('Auth bootstrap: initData still missing after retries, will rely on headers')
      setAuthError(
        'Telegram не передал initData. Попробуем авторизоваться через заголовок. Если ошибка повторится — пришлите значения ниже.',
      )
      setShowDebug(true)
    }

    inflightRef.current = true
    const payload: Record<string, unknown> = {}
    if (resolvedInitData) {
      payload.initData = resolvedInitData
    }
    if (referralCode) {
      payload.referralCode = referralCode
    }
    if (utmSource) {
      payload.utmSource = utmSource
    }
    if (utmMedium) {
      payload.utmMedium = utmMedium
    }
    if (utmCampaign) {
      payload.utmCampaign = utmCampaign
    }

    const run = async () => {
      try {
        const response = await apiClient<{
          token: string
          expiresIn: number
          user: {
            id: number
            telegramId: number
            username?: string | null
            firstName?: string | null
            lastName?: string | null
            betaEnabled: boolean
            timezone?: string | null
            plan?: string | null
          }
        }>('/auth', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        })

        window.localStorage.setItem(AUTH_STORAGE_KEY, response.token)
        window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(response.user))
        const { setBetaMode } = useSettingsStore.getState()
        setBetaMode(Boolean(response.user.betaEnabled))
        queryClient.removeQueries({ queryKey: ['beta-status'] })
        queryClient.invalidateQueries()
        setAuthError(undefined)
        setShowDebug(false)
      } catch (error) {
        console.warn('Auth bootstrap failed', error)
        setAuthError(
          error instanceof Error
            ? `Ошибка авторизации: ${error.message}`
            : 'Ошибка авторизации в мини-приложении',
        )
        setShowDebug(true)
      } finally {
        inflightRef.current = false
        setAttempted(true)
      }
    }

    run()
    return () => {}  // keep diagnostic data until next attempt
  }, [attempted, initDataRaw, isReady, queryClient, retryCount, setAuthError, updateDebugInfo, setShowDebug])

  if (localDebugInfo) {
    console.info('[AuthBootstrap::initData]', localDebugInfo)
  }

  return null
}
