import apiClient from './client'
import type {
  UserSettings,
  UpdateSettingsRequest,
} from '@/types/api.types'

export const settingsApi = {
  /**
   * Get current user settings
   */
  getSettings: async (): Promise<UserSettings> => {
    const response = await apiClient.get<UserSettings>('/settings')
    return response.data
  },

  /**
   * Update user settings
   */
  updateSettings: async (request: UpdateSettingsRequest): Promise<UserSettings> => {
    const response = await apiClient.put<UserSettings>('/settings', request)
    return response.data
  },
}
