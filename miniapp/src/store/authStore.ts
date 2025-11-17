import { create } from 'zustand'

interface AuthState {
  error?: string
  initDataRaw?: string
  webAppInitData?: string
  initDataUnsafe?: string
  shouldShowDebug: boolean
  setError: (message?: string) => void
  setDebugInfo: (payload: {
    initDataRaw?: string
    webAppInitData?: string
    initDataUnsafe?: string
  }) => void
  setShowDebug: (value: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  error: undefined,
  initDataRaw: undefined,
  webAppInitData: undefined,
  initDataUnsafe: undefined,
  shouldShowDebug: false,
  setError: (message) => set({ error: message }),
  setDebugInfo: ({ initDataRaw, webAppInitData, initDataUnsafe }) =>
    set({ initDataRaw, webAppInitData, initDataUnsafe }),
  setShowDebug: (value) => set({ shouldShowDebug: value }),
}))
