import { apiClient } from '@/lib/api-client'

interface BetaStatusResponse {
  enabled: boolean
}

export const settingsApi = {
  async fetchBetaStatus(): Promise<BetaStatusResponse> {
    return apiClient<BetaStatusResponse>(`/user/beta?t=${Date.now()}`)
  },

  async updateBetaStatus(enabled: boolean): Promise<BetaStatusResponse> {
    return apiClient<BetaStatusResponse>(`/user/beta?t=${Date.now()}`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    })
  },
}
