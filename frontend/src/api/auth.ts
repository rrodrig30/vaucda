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
   * Logout (clear local storage)
   */
  logout: async (): Promise<void> => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  },

  /**
   * Refresh token
   */
  refreshToken: async (): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>('/auth/refresh')
    return response.data
  },
}
