import apiClient from './client'
import type {
  EvidenceSearchRequest,
  EvidenceSearchResponse,
  DocumentIngestionRequest,
  DocumentIngestionResponse,
} from '@/types/api.types'

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
   */
  uploadDocuments: async (formData: FormData): Promise<any> => {
    const response = await apiClient.post('/rag/upload-documents', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
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
