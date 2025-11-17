import {
  IconInfoCircle,
  IconMinus,
  IconMoonStars,
  IconPlus,
  IconWorld,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Card } from '@/components/common/Card'
import { Chip } from '@/components/common/Chip'
import { useTelegram } from '@/app/hooks/useTelegram'
import {
  MAX_TIMEZONE_OFFSET,
  MIN_TIMEZONE_OFFSET,
  useSettingsStore,
} from '@/store/settingsStore'
import { settingsApi } from '@/features/settings/api/settingsApi'

const formatTimezone = (offset: number) => {
  if (!Number.isFinite(offset)) return '+0'
  if (offset === 0) return '+0'
  return offset > 0 ? `+${offset}` : `${offset}`
}

export const SettingsPage = () => {
  const { initData, colorScheme } = useTelegram()
  const timezone = useSettingsStore((state) => state.timezone)
  const betaMode = useSettingsStore((state) => state.betaMode)
  const betaInitialized = useSettingsStore((state) => state.betaInitialized)
  const setTimezone = useSettingsStore((state) => state.setTimezone)
  const setBetaMode = useSettingsStore((state) => state.setBetaMode)
  const queryClient = useQueryClient()
  const betaStatusQuery = useQuery({
    queryKey: ['beta-status'],
    queryFn: () => settingsApi.fetchBetaStatus(),
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (betaStatusQuery.data) {
      setBetaMode(betaStatusQuery.data.enabled)
    }
  }, [betaStatusQuery.data, setBetaMode])

  const updateBetaMutation = useMutation({
    mutationFn: (enabled: boolean) => settingsApi.updateBetaStatus(enabled),
    onSuccess: (data) => {
      setBetaMode(data.enabled)
      queryClient.setQueryData(['beta-status'], data)
      queryClient.invalidateQueries({ queryKey: ['beta-status'] })
    },
    onError: (error) => {
      console.error('Failed to toggle beta', error)
      const message = error instanceof Error ? error.message : 'Не удалось обновить бета-режим. Попробуйте ещё раз.'
      window.alert(message)
    },
  })

  const handleEnableBeta = () => {
    updateBetaMutation.mutate(true)
  }

  const handleDisableBeta = () => {
    updateBetaMutation.mutate(false)
  }

  const handleDecreaseTimezone = () => setTimezone(timezone - 1)
  const handleIncreaseTimezone = () => setTimezone(timezone + 1)
  const canDecreaseTimezone = timezone > MIN_TIMEZONE_OFFSET
  const canIncreaseTimezone = timezone < MAX_TIMEZONE_OFFSET

  if (!betaInitialized) {
    return (
      <section className="page settings-page">
        <div className="app-loader">Загрузка настроек…</div>
      </section>
    )
  }

  if (!betaMode) {
    return (
      <section className="page settings-page">
        <Card className="settings-section">
          <header>
            <h3>
              <IconInfoCircle size={18} stroke={1.8} /> Включите beta-режим
            </h3>
            <p>Веб-приложение работает только в beta-режиме. Активируйте его, чтобы продолжить.</p>
          </header>
          <div className="settings-beta">
            <p className="settings-beta__note">
              После включения станут доступны остальные настройки и функции приложения.
            </p>
            <button
              type="button"
              className="settings-beta__button"
              onClick={handleEnableBeta}
              disabled={updateBetaMutation.isPending}
            >
              {updateBetaMutation.isPending ? 'Включаем...' : 'Включить beta-режим'}
            </button>
          </div>
        </Card>
      </section>
    )
  }

  return (
    <section className="page settings-page">
      <Card className="settings-section">
        <header>
          <h3>
            <IconInfoCircle size={18} stroke={1.8} /> Beta-режим активен
          </h3>
          <p>Вы получаете доступ к экспериментальным возможностям веб-приложения.</p>
        </header>
        <div className="settings-beta settings-beta--active">
          <Chip active>Beta включён</Chip>
          <button
            type="button"
            className="settings-beta__button settings-beta__button--ghost"
              onClick={handleDisableBeta}
              disabled={updateBetaMutation.isPending}
          >
            {updateBetaMutation.isPending ? 'Выключаем...' : 'Выключить beta-режим'}
          </button>
        </div>
      </Card>

      <Card className="settings-section">
        <header>
          <h3>
            <IconWorld size={18} stroke={1.8} /> Временная зона
          </h3>
          <p>Укажите смещение от UTC для корректного отображения событий в календаре.</p>
        </header>
        <div className="settings-timezone">
          <div className="settings-timezone__control">
            <button
              type="button"
              onClick={handleDecreaseTimezone}
              disabled={!canDecreaseTimezone}
              aria-label="Уменьшить смещение"
            >
              <IconMinus size={16} stroke={2} />
            </button>
            <span className="settings-timezone__value">UTC{formatTimezone(timezone)}</span>
            <button
              type="button"
              onClick={handleIncreaseTimezone}
              disabled={!canIncreaseTimezone}
              aria-label="Увеличить смещение"
            >
              <IconPlus size={16} stroke={2} />
            </button>
          </div>
          <p className="settings-timezone__hint">
            Доступный диапазон: от {formatTimezone(MIN_TIMEZONE_OFFSET)} до{' '}
            {formatTimezone(MAX_TIMEZONE_OFFSET)}.
          </p>
        </div>
      </Card>

      <Card className="settings-section">
        <header>
          <h3>
            <IconMoonStars size={18} stroke={1.8} /> Оформление
          </h3>
          <p>Цветовая схема синхронизирована с клиентом Telegram.</p>
        </header>
        <div className="settings-theme">
          <Chip active>Тема: {colorScheme}</Chip>
          <p>
            Используем параметры mini app: фон, кнопки, текст — применяются автоматически из{' '}
            Telegram WebApp API.
          </p>
        </div>
      </Card>

      <Card className="settings-section">
        <header>
          <h3>
            <IconInfoCircle size={18} stroke={1.8} /> Профиль Telegram
          </h3>
          <p>Убедитесь, что пользователь прошёл валидацию через initData.</p>
        </header>
        {initData?.user ? (
          <div className="settings-telegram">
            <div>
              <span className="settings-telegram__name">
                {initData.user.first_name} {initData.user.last_name}
              </span>
              <p>ID: {initData.user.id}</p>
            </div>
            {initData.user.username && <Chip>@{initData.user.username}</Chip>}
          </div>
        ) : (
          <p className="settings-note">Данные пользователя будут доступны внутри Telegram Mini App.</p>
        )}
      </Card>
    </section>
  )
}
