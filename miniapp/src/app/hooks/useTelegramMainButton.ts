import { useEffect } from 'react'
import { useTelegram } from './useTelegram'

interface TelegramMainButtonOptions {
  text: string
  visible?: boolean
  enabled?: boolean
  isLoading?: boolean
  onClick?: () => void
}

export const useTelegramMainButton = ({
  text,
  visible = false,
  enabled = true,
  isLoading = false,
  onClick,
}: TelegramMainButtonOptions) => {
  const { webApp, isReady } = useTelegram()

  useEffect(() => {
    if (!webApp || !isReady) return
    const mainButton = webApp.MainButton

    if (!visible) {
      mainButton.hide()
      return
    }

    const handler = () => onClick?.()
    mainButton.setText(text)
    if (enabled) {
      mainButton.enable()
    } else {
      mainButton.disable()
    }
    mainButton.show()

    if (onClick) {
      mainButton.onClick(handler)
    }

    return () => {
      if (onClick) {
        mainButton.offClick(handler)
      }
      mainButton.hide()
    }
  }, [webApp, isReady, text, visible, enabled, onClick])

  useEffect(() => {
    if (!webApp || !isReady) return
    if (!visible) return
    const mainButton = webApp.MainButton
    if (isLoading) {
      mainButton.showProgress()
    } else {
      mainButton.hideProgress()
    }
  }, [webApp, isReady, visible, isLoading])
}
