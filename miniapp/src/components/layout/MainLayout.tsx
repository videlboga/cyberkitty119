import { Suspense, useEffect, useRef } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { IconInfoCircle } from '@tabler/icons-react'
import { Card } from '@/components/common/Card'
import { useSettingsStore } from '@/store/settingsStore'
import { useAuthStore } from '@/store/authStore'
import { DebugInitData } from '@/components/DebugInitData'
import { BottomNav } from './BottomNav'
import { settingsApi } from '@/features/settings/api/settingsApi'
import {
  cleanStartParamFromUrl,
  clearStoredStartParam,
  readStartParam,
  resolveStartParamToPath,
} from '@/lib/startParam'

export const MainLayout = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const authError = useAuthStore((state) => state.error)
  const shouldShowDebug = useAuthStore((state) => state.shouldShowDebug)
  const initDataRaw = useAuthStore((state) => state.initDataRaw)
  const webAppInitData = useAuthStore((state) => state.webAppInitData)
  const initDataUnsafe = useAuthStore((state) => state.initDataUnsafe)
  const betaMode = useSettingsStore((state) => state.betaMode)
  const betaInitialized = useSettingsStore((state) => state.betaInitialized)
  const setBetaMode = useSettingsStore((state) => state.setBetaMode)
  const isNoteEditor = location.pathname.startsWith('/notes/')
  const betaStatusQuery = useQuery({
    queryKey: ['beta-status'],
    queryFn: () => settingsApi.fetchBetaStatus(),
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    staleTime: 0,
  })
  const enableBetaMutation = useMutation({
    mutationFn: async () => {
      return settingsApi.updateBetaStatus(true)
    },
    onSuccess: (data) => {
      setBetaMode(data.enabled)
      betaStatusQuery.refetch()
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Не удалось включить beta-режим. Попробуйте ещё раз.'
      window.alert(message)
    },
  })

  useEffect(() => {
    if (!betaStatusQuery.isFetching && betaStatusQuery.isSuccess) {
      const enabled = Boolean(betaStatusQuery.data?.enabled)
      if (enabled !== betaMode) {
        setBetaMode(enabled)
      }
    }
  }, [betaStatusQuery.isFetching, betaStatusQuery.isSuccess, betaStatusQuery.data, betaMode, setBetaMode])

  const processedStartParamRef = useRef<{
    raw: string
    path: string
    navigated: boolean
    cleaned: boolean
  } | null>(null)

  useEffect(() => {
    if (!betaInitialized || !betaMode) {
      return
    }

    const rawStartParam = readStartParam()
    if (!rawStartParam) {
      return
    }

    const targetPath = resolveStartParamToPath(rawStartParam)

    if (!targetPath) {
      clearStoredStartParam()
      cleanStartParamFromUrl()
      return
    }

    const currentLocation = `${location.pathname}${location.search ?? ''}`

    if (
      !processedStartParamRef.current ||
      processedStartParamRef.current.raw !== rawStartParam ||
      processedStartParamRef.current.path !== targetPath
    ) {
      processedStartParamRef.current = {
        raw: rawStartParam,
        path: targetPath,
        navigated: currentLocation === targetPath,
        cleaned: false,
      }
    }

    const state = processedStartParamRef.current

    if (!state.cleaned && currentLocation === targetPath) {
      clearStoredStartParam()
      cleanStartParamFromUrl()
      processedStartParamRef.current = { ...state, navigated: true, cleaned: true }
      return
    }

    if (!state.navigated && currentLocation !== targetPath) {
      processedStartParamRef.current = { ...state, navigated: true }
      navigate(targetPath, { replace: true })
      return
    }

    if (state.navigated && !state.cleaned && currentLocation !== targetPath) {
      processedStartParamRef.current = { ...state, navigated: false }
    }
  }, [betaInitialized, betaMode, location.pathname, location.search, navigate])

  useEffect(() => {
    if (!betaInitialized) {
      return
    }
    if (!betaMode && location.pathname !== '/') {
      navigate('/', { replace: true })
    }
  }, [betaInitialized, betaMode, location.pathname, navigate])

  if (!betaInitialized) {
    return (
      <div className="app-shell">
        <main className="app-content">
          <div className="app-loader">Загрузка…</div>
        </main>
      </div>
    )
  }

  if (authError) {
    return (
      <div className="app-shell">
        <main className="app-content">
          <section className="page beta-gate">
            <Card className="beta-gate__card">
              <header>
                <h3>
                  <IconInfoCircle size={18} stroke={1.8} /> Не удалось авторизоваться
                </h3>
                <p>
                  {authError}
                </p>
              </header>
              <div className="settings-beta">
                <p className="settings-beta__note">
                  Убедитесь, что мини-приложение открыто внутри Telegram (iOS/Android). В веб-версии
                  подключение может быть недоступно.
                </p>
              </div>
            </Card>
            {shouldShowDebug && (
              <DebugInitData
                initDataRaw={initDataRaw}
                webAppInitData={webAppInitData}
                initDataUnsafe={initDataUnsafe}
              />
            )}
          </section>
        </main>
      </div>
    )
  }

  if (!betaMode) {
    return (
      <div className="app-shell">
        <main className="app-content">
          <section className="page beta-gate">
            <Card className="beta-gate__card">
              <header>
                <h3>
                  <IconInfoCircle size={18} stroke={1.8} /> Доступно в beta-режиме
                </h3>
                <p>Веб-приложение сейчас работает только в beta. Включите режим, чтобы продолжить.</p>
              </header>
              <div className="settings-beta">
                <p className="settings-beta__note">
                  Режим открывает доступ ко всем заметкам, агенту и группам. Вы сможете отключить его
                  в настройках.
                </p>
                <button
                  type="button"
                  className="settings-beta__button"
                  onClick={() => enableBetaMutation.mutate()}
                  disabled={enableBetaMutation.isPending}
                >
                  {enableBetaMutation.isPending ? 'Включаем…' : 'Включить beta-режим'}
                </button>
              </div>
            </Card>
          </section>
        </main>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <main className={isNoteEditor ? 'app-editor' : 'app-content'}>
        <Suspense fallback={<div className="app-loader">Загрузка...</div>}>
          <Outlet />
        </Suspense>
      </main>
      {!isNoteEditor && <BottomNav currentPath={location.pathname} />}
    </div>
  )
}
