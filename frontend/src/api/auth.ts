import apiClient from './client'
import type { LoginRequest, LoginResponse, User, RegisterRequest, RegisterResponse } from '@/types/api.types'

export const authApi = {
  /**
   * Register a new user
   */
  register: async (data: RegisterRequest): Promise<RegisterResponse> => {
    const response = await apiClient.post<RegisterResponse>('/auth/register', data)
    return response.data
  },

  /**
   * Login with username and password
   */
  login: async (credentials: LoginRequest): Promise<LoginResponse> => {
    const formData = new URLSearchParams()
    formData.append('username', credentials.username)
    formData.append('password', credentials.password)

    const response = await apiClient.post<LoginResponse>('/auth/token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    })
    return response.data
  },

  /**
   * Get current user profile
   */
  getCurrentUser: async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me')
    return response.data
  },

  /**
   * Logout - calls backend to purge patient data, then clears local storage
   * CRITICAL: Must call backend first to ensure patient data is purged (HIPAA compliance)
   */
  logout: async (): Promise<void> => {
    try {
      // CRITICAL: Call backend to purge all patient data before clearing tokens
      await apiClient.post('/auth/logout')
    } catch (error) {
      // Log error but continue with local cleanup
      console.warn('Backend logout failed, continuing with local cleanup:', error)
    } finally {
      // Always clear local storage regardless of backend response
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
    }
  },

  /**
   * Refresh access token using stored refresh token
   * Returns new access_token and refresh_token pair
   */
  refreshToken: async (): Promise<LoginResponse> => {
    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      throw new Error('No refresh token available')
    }
    const response = await apiClient.post<LoginResponse>('/auth/refresh', {
      refresh_token: refreshToken
    })
    // Update stored tokens with new values
    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token)
    }
    if (response.data.refresh_token) {
      localStorage.setItem('refresh_token', response.data.refresh_token)
    }
    return response.data
  },
}
