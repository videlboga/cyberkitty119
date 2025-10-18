import { useMemo } from 'react'
import { Card } from '@/components/common/Card'

type Props = {
  initDataRaw?: string
  webAppInitData?: string
  initDataUnsafe?: string
}

export const DebugInitData = ({ initDataRaw, webAppInitData, initDataUnsafe }: Props) => {
  const items = useMemo(
    () => [
      { label: 'initDataRaw (context)', value: initDataRaw || '—' },
      { label: 'Telegram.WebApp.initData', value: webAppInitData || '—' },
      { label: 'Telegram.WebApp.initDataUnsafe', value: initDataUnsafe || '—' },
    ],
    [initDataRaw, webAppInitData, initDataUnsafe],
  )

  return (
    <Card className="debug-card">
      <header>
        <h3>Диагностика initData</h3>
        <p>Передайте скрин мне или в лог — поможет восстановить авторизацию.</p>
      </header>
      <dl className="debug-card__list">
        {items.map(({ label, value }) => (
          <div key={label} className="debug-card__item">
            <dt>{label}</dt>
            <dd className="debug-card__value">
              <pre>{value}</pre>
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}
