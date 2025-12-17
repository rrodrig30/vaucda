import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types/api.types'

// Get API base URL - empty string means use the dev server proxy
const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL ? `${BASE_URL}/api/v1` : '/api/v1',
  timeout: 1200000, // 20 minutes for multi-GPU batch processing (handles up to 13 AI sections)
  maxContentLength: 10 * 1024 * 1024, // 10MB max response size
  maxBodyLength: 10 * 1024 * 1024, // 10MB max request body size (for large clinical data pastes)
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    if (error.response?.status === 401) {
      // Token expired or invalid - clear auth and redirect to login
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }

    // Format error message
    const apiError: ApiError = {
      detail: error.response?.data?.detail || error.message || 'An error occurred',
      error_code: error.response?.data?.error_code,
      errors: error.response?.data?.errors,
    }

    return Promise.reject(apiError)
  }
)

export default apiClient
