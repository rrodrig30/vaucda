import apiClient from './client'
import type { HealthCheck, DetailedHealthCheck } from '@/types/api.types'

export const healthApi = {
  /**
   * General health check (no authentication required)
   */
  getHealth: async (): Promise<HealthCheck> => {
    const response = await apiClient.get<HealthCheck>('/health')
    return response.data
  },

  /**
   * Detailed health check (authentication required)
   */
  getDetailedHealth: async (): Promise<DetailedHealthCheck> => {
    const response = await apiClient.get<DetailedHealthCheck>('/health/detailed')
    return response.data
  },
}
