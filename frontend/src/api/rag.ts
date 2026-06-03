import axios from 'axios'
import apiClient from './client'
import type {
  EvidenceSearchRequest,
  EvidenceSearchResponse,
  DocumentIngestionRequest,
  DocumentIngestionResponse,
} from '@/types/api.types'

/**
 * Check if a JWT token is expired or will expire within the buffer time
 * @param token JWT access token
 * @param bufferSeconds Consider expired if within this many seconds of expiry (default 60)
 */
function isTokenExpired(token: string | null, bufferSeconds: number = 60): boolean {
  if (!token) return true
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    const exp = payload.exp
    if (!exp) return true
    const nowSeconds = Math.floor(Date.now() / 1000)
    return nowSeconds >= (exp - bufferSeconds)
  } catch {
    return true
  }
}

/**
 * Refresh the access token using the stored refresh token
 * @returns New access token or null if refresh failed
 */
async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) {
    console.warn('No refresh token available for token refresh')
    return null
  }

  try {
    console.log('Attempting to refresh access token...')
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const refreshUrl = baseURL ? `${baseURL}/api/v1/auth/refresh` : '/api/v1/auth/refresh'
    const response = await axios.post(refreshUrl, {
      refresh_token: refreshToken
    })
    const newAccessToken = response.data.access_token
    const newRefreshToken = response.data.refresh_token

    if (newAccessToken) {
      localStorage.setItem('access_token', newAccessToken)
      console.log('Access token refreshed successfully')
    }
    if (newRefreshToken) {
      localStorage.setItem('refresh_token', newRefreshToken)
    }
    return newAccessToken
  } catch (error: any) {
    console.error('Token refresh failed:', error.message)
    return null
  }
}

/**
 * Get a valid access token, refreshing if necessary
 */
async function getValidToken(): Promise<string | null> {
  let token = localStorage.getItem('access_token')

  // If token is expired or near expiry, try to refresh
  if (isTokenExpired(token)) {
    console.log('Access token expired or near expiry, refreshing...')
    token = await refreshAccessToken()
  }

  return token
}

export const ragApi = {
  /**
   * Search clinical knowledge base using RAG
   */
  search: async (request: EvidenceSearchRequest): Promise<EvidenceSearchResponse> => {
    const response = await apiClient.post<EvidenceSearchResponse>('/rag/search', request)
    return response.data
  },

  /**
   * Upload multiple documents to build knowledge base
   *
   * Uses fetch() with streaming response to handle long-running uploads.
   * The backend returns NDJSON (newline-delimited JSON) with progress updates
   * to keep the connection alive during processing (which can take 60-90+ seconds).
   *
   * Token handling:
   * - Checks token expiration before upload, refreshes if needed
   * - On 401 error, attempts one token refresh and retry
   */
  uploadDocuments: async (formData: FormData, onProgress?: (progress: any) => void): Promise<any> => {
    console.log('=== RAG Upload Starting (Streaming) ===')
    console.log('FormData entries:', Array.from(formData.entries()).length)

    // Get valid auth token (refresh if expired)
    let token = await getValidToken()
    if (!token) {
      console.error('No valid token available for upload')
      throw new Error('Authentication required. Please log in again.')
    }

    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const backendUrl = baseURL
      ? `${baseURL}/api/v1/rag/upload-documents`
      : '/api/v1/rag/upload-documents'

    const makeStreamingUploadRequest = async (authToken: string): Promise<any> => {
      const response = await fetch(backendUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          // Don't set Content-Type for FormData - browser sets it with boundary
        },
        body: formData,
      })

      if (response.status === 401) {
        throw { status: 401, message: 'Unauthorized' }
      }

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Upload failed: ${response.status} ${errorText}`)
      }

      // Read streaming NDJSON response
      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let finalResult: any = null

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Process complete lines
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue

          try {
            const data = JSON.parse(line)
            console.log('Stream message:', data.type, data.message || '')

            if (data.type === 'progress' || data.type === 'heartbeat') {
              if (onProgress) {
                onProgress(data)
              }
            } else if (data.type === 'complete') {
              finalResult = data
              console.log('=== RAG Upload Complete ===')
              console.log('Processed files:', data.processed?.length || 0)
            } else if (data.type === 'error') {
              throw new Error(data.message || 'Upload failed')
            }
          } catch (parseError) {
            console.warn('Failed to parse stream line:', line)
          }
        }
      }

      // Process any remaining data in buffer
      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer)
          if (data.type === 'complete') {
            finalResult = data
          }
        } catch {
          // Ignore parse errors for incomplete data
        }
      }

      if (!finalResult) {
        throw new Error('No completion message received from server')
      }

      return finalResult
    }

    try {
      return await makeStreamingUploadRequest(token)
    } catch (error: any) {
      // On 401, try to refresh token and retry once
      if (error.status === 401) {
        console.log('Upload received 401, attempting token refresh and retry...')
        const newToken = await refreshAccessToken()
        if (newToken) {
          try {
            return await makeStreamingUploadRequest(newToken)
          } catch (retryError: any) {
            console.error('=== RAG Upload Failed After Retry ===')
            console.error('Error:', retryError.message)
            throw retryError
          }
        } else {
          console.error('Token refresh failed, cannot retry upload')
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('user')
          window.location.href = '/login'
          throw new Error('Session expired. Please log in again.')
        }
      }

      console.error('=== RAG Upload Error ===')
      console.error('Error:', error.message || error)
      throw error
    }
  },

  /**
   * Get system prompt for urology note generation
   */
  getSystemPrompt: async (): Promise<any> => {
    const response = await apiClient.get('/rag/system-prompt')
    return response.data
  },

  /**
   * Update system prompt (admin only)
   */
  updateSystemPrompt: async (prompt: string): Promise<any> => {
    const formData = new FormData()
    formData.append('prompt', prompt)

    const response = await apiClient.post('/rag/system-prompt', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },

  /**
   * Get knowledge base statistics
   */
  getStats: async (): Promise<any> => {
    const response = await apiClient.get('/rag/stats')
    return response.data
  },

  /**
   * Ingest a new document into the knowledge base (admin only)
   */
  ingestDocument: async (request: DocumentIngestionRequest): Promise<DocumentIngestionResponse> => {
    const formData = new FormData()
    formData.append('file', request.file)
    formData.append('title', request.title)
    formData.append('source', request.source)
    formData.append('document_type', request.document_type)
    formData.append('category', request.category)

    const response = await apiClient.post<DocumentIngestionResponse>(
      '/evidence/ingest',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data
  },
}
