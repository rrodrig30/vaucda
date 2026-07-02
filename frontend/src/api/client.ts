import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types/api.types'

// Get API base URL - empty string means use the dev server proxy
const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const API_PREFIX = BASE_URL ? `${BASE_URL}/api/v1` : '/api/v1'

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_PREFIX,
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

const formatError = (error: AxiosError<ApiError>): ApiError => ({
  detail: error.response?.data?.detail || error.message || 'An error occurred',
  error_code: error.response?.data?.error_code,
  errors: error.response?.data?.errors,
})

const clearAuthAndRedirect = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// ---- Silent token refresh on 401 -----------------------------------------
// The access token has an 8h TTL and long batch jobs outlive it. Instead of
// hard-failing on 401, exchange the stored refresh_token for a fresh access
// token and transparently retry the original request. Concurrent 401s during
// a single refresh are coalesced so only ONE /auth/refresh call is made.
let isRefreshing = false
let pendingQueue: Array<{
  resolve: (token: string) => void
  reject: (err: unknown) => void
}> = []

const flushQueue = (error: unknown, token: string | null) => {
  pendingQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token as string)))
  pendingQueue = []
}

// Response interceptor: silent refresh-and-retry on 401, else format the error.
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    const status = error.response?.status

    // Never try to refresh the auth endpoints themselves (avoids recursion).
    const url = original?.url || ''
    const isAuthCall =
      url.includes('/auth/refresh') || url.includes('/auth/login') || url.includes('/auth/token')

    if (status === 401 && original && !original._retry && !isAuthCall) {
      const refreshToken = localStorage.getItem('refresh_token')
      if (!refreshToken) {
        clearAuthAndRedirect()
        return Promise.reject(formatError(error))
      }
      original._retry = true

      // A refresh is already in flight — queue this request, retry once it lands.
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push({
            resolve: (token: string) => {
              if (original.headers) original.headers.Authorization = `Bearer ${token}`
              resolve(apiClient(original))
            },
            reject,
          })
        })
      }

      isRefreshing = true
      try {
        // Bare axios (not apiClient) so the request interceptor doesn't attach
        // the stale token and the response interceptor doesn't recurse.
        const resp = await axios.post(
          `${API_PREFIX}/auth/refresh`,
          { refresh_token: refreshToken },
          { headers: { 'Content-Type': 'application/json' }, timeout: 30000 }
        )
        const newAccess: string = resp.data.access_token
        const newRefresh: string | undefined = resp.data.refresh_token
        localStorage.setItem('access_token', newAccess)
        if (newRefresh) localStorage.setItem('refresh_token', newRefresh)

        flushQueue(null, newAccess)
        if (original.headers) original.headers.Authorization = `Bearer ${newAccess}`
        return apiClient(original)
      } catch (refreshErr) {
        // Refresh token also expired/invalid — back to login.
        flushQueue(refreshErr, null)
        clearAuthAndRedirect()
        return Promise.reject(formatError(error))
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(formatError(error))
  }
)

export default apiClient
