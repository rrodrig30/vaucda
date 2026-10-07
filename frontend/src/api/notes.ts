import apiClient from './client'
import type {
  NoteGenerationRequest,
  NoteGenerationResponse,
  SavedNote,
  InitialNoteRequest,
  InitialNoteResponse,
  FinalNoteRequest,
  FinalNoteResponse,
  DocumentUploadResponse,
  BatchProcessingRequest,
  BatchProcessingResponse,
  BatchFolderListResponse,
  BatchProgressEvent,
  BrowseDirectoryResponse,
} from '@/types/api.types'

export const notesApi = {
  /**
   * Generate a clinical note (respects llm_provider choice)
   */
  generateNote: async (request: NoteGenerationRequest): Promise<NoteGenerationResponse> => {
    const response = await apiClient.post<NoteGenerationResponse>('/notes/generate', request)
    return response.data
  },

  /**
   * Retrieve a previously generated note
   */
  getNote: async (noteId: string): Promise<SavedNote> => {
    const response = await apiClient.get<SavedNote>(`/notes/${noteId}`)
    return response.data
  },

  // HIPAA COMPLIANCE: getRecentNotes removed - notes are ephemeral only
  // No note history retrieval to prevent cross-patient contamination

  // ============================================================================
  // DOCUMENT UPLOAD (OCR Support)
  // ============================================================================

  /**
   * Upload a clinical document (PDF or TXT) for Stage 1 note generation.
   *
   * For image-based PDFs (scanned documents), automatically uses OCR
   * via Ollama glm-ocr model.
   *
   * @param file - PDF or TXT file to process
   * @returns Extracted text and metadata
   */
  uploadDocument: async (file: File): Promise<DocumentUploadResponse> => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await apiClient.post<DocumentUploadResponse>(
      '/notes/upload-document',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 1800000, // 30 minutes for OCR processing (large vision models ~1-2 min/page)
      }
    )
    return response.data
  },

  // ============================================================================
  // TWO-STAGE WORKFLOW API METHODS
  // ============================================================================

  /**
   * STAGE 1: Generate initial note with calculator suggestions
   *
   * This endpoint:
   * 1. Organizes clinical data into structured preliminary note
   * 2. Extracts clinical entities using NLP
   * 3. Suggests relevant calculators based on detected data
   * 4. Returns note WITHOUT Assessment & Plan
   */
  generateInitialNote: async (request: InitialNoteRequest): Promise<InitialNoteResponse> => {
    const response = await apiClient.post<InitialNoteResponse>('/notes/generate-initial', request)
    return response.data
  },

  /**
   * STAGE 2: Generate final note with Assessment & Plan
   *
   * This endpoint:
   * 1. Executes selected clinical calculators
   * 2. Retrieves evidence from RAG (if enabled)
   * 3. Generates comprehensive Assessment & Plan
   * 4. Integrates calculator results and clinical discussion
   * 5. Returns complete note ready for documentation
   */
  generateFinalNote: async (request: FinalNoteRequest): Promise<FinalNoteResponse> => {
    const response = await apiClient.post<FinalNoteResponse>('/notes/generate-final', request)
    return response.data
  },

  /**
   * EXPRESS: Run Stage 1 + Stage 2 in one call without calculator selection.
   *
   * Skips entity extraction and calculator suggestion. Produces the final
   * note (with A&P, no calculators) directly.
   */
  generateExpressNote: async (request: InitialNoteRequest): Promise<FinalNoteResponse> => {
    const response = await apiClient.post<FinalNoteResponse>('/notes/generate-express', request, {
      // Allow up to 30 minutes — Express does both Stage 1 and Stage 2
      timeout: 1800000,
    })
    return response.data
  },

  /**
   * EXPRESS (streaming): same as generateExpressNote but streams Server-Sent
   * Events so the UI can display progress (Stage 1 / RAG / Stage 2) while
   * the multi-minute LLM workflow runs.
   *
   * Returns a controller with abort(); calls callbacks for each event.
   */
  generateExpressNoteStream: (
    request: InitialNoteRequest,
    callbacks: {
      onStage1Start?: (data: { message: string; model?: string; provider?: string }) => void
      onStage1Complete?: (data: { length: number; elapsed_seconds: number }) => void
      onRagStart?: (data: { queries: string[] }) => void
      onRagSkipped?: (data: { reason: string }) => void
      onRagComplete?: (data: { sources_count: number; context_chars?: number; error?: string }) => void
      onStage2Start?: (data: { message: string; model?: string; provider?: string }) => void
      onStage2Complete?: (data: { length: number; elapsed_seconds: number }) => void
      onComplete?: (data: FinalNoteResponse) => void
      onError?: (detail: string) => void
    }
  ): { abort: () => void } => {
    const controller = new AbortController()
    const token = localStorage.getItem('access_token')
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    const url = baseUrl
      ? `${baseUrl}/api/v1/notes/generate-express-stream`
      : '/api/v1/notes/generate-express-stream'

    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
          callbacks.onError?.(err.detail || `HTTP ${response.status}`)
          return
        }
        const reader = response.body?.getReader()
        if (!reader) {
          callbacks.onError?.('No response stream available')
          return
        }
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const events = buffer.split('\n\n')
          buffer = events.pop() || ''
          for (const block of events) {
            if (!block.trim()) continue
            let evt = ''
            const dataLines: string[] = []
            for (const line of block.split('\n')) {
              if (line.startsWith('event: ')) evt = line.slice(7).trim()
              else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
              else if (line.startsWith('data:')) dataLines.push(line.slice(5))
            }
            if (!evt || dataLines.length === 0) continue
            try {
              const parsed = JSON.parse(dataLines.join('\n'))
              switch (evt) {
                case 'stage1_start': callbacks.onStage1Start?.(parsed); break
                case 'stage1_complete': callbacks.onStage1Complete?.(parsed); break
                case 'rag_start': callbacks.onRagStart?.(parsed); break
                case 'rag_skipped': callbacks.onRagSkipped?.(parsed); break
                case 'rag_complete': callbacks.onRagComplete?.(parsed); break
                case 'stage2_start': callbacks.onStage2Start?.(parsed); break
                case 'stage2_complete': callbacks.onStage2Complete?.(parsed); break
                case 'complete': callbacks.onComplete?.(parsed as FinalNoteResponse); break
                case 'error': callbacks.onError?.(parsed.detail || 'Unknown error'); break
              }
            } catch (e) {
              console.warn('SSE parse error:', e)
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') callbacks.onError?.(err.message || 'Connection failed')
      })

    return { abort: () => controller.abort() }
  },

  // ============================================================================
  // SESSION MANAGEMENT (Cross-Patient Contamination Prevention)
  // ============================================================================

  /**
   * Start a new patient session - PURGES all previous patient data
   *
   * CRITICAL: Call this when:
   * - User clicks "New Patient" button
   * - User clicks "Clear Note" button
   * - Before starting work on a different patient
   *
   * This ensures complete data isolation between patients (HIPAA compliance).
   */
  startNewSession: async (): Promise<{ status: string; message: string; session_id: string }> => {
    const response = await apiClient.post<{ status: string; message: string; session_id: string }>(
      '/notes/new-session'
    )
    return response.data
  },

  /**
   * End current patient session and purge all data
   *
   * CRITICAL: Call this when user is done with a patient
   */
  endSession: async (): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post<{ status: string; message: string }>('/notes/end-session')
    return response.data
  },

  /**
   * Get current session status (for debugging/monitoring)
   */
  getSessionStatus: async (): Promise<{
    session_active: boolean
    session_id: string | null
    created_at?: string
    has_clinical_input?: boolean
    has_preliminary_note?: boolean
    has_embeddings?: boolean
    message?: string
  }> => {
    const response = await apiClient.get('/notes/session-status')
    return response.data
  },

  // ============================================================================
  // BATCH PROCESSING
  // ============================================================================

  /**
   * Upload and batch process .txt files with SSE streaming.
   *
   * Each completed note is streamed back immediately so the frontend
   * can save it as a file — no waiting for the entire batch.
   *
   * Events: file_start, file_complete (includes note_content),
   *         file_failed, total (total.vaucda content), complete, error
   */
  batchUploadProcessStream: (
    files: File[],
    options: { visitDate?: string; noteType?: string },
    callbacks: {
      onFileStart?: (data: { filename: string; output_filename: string; note_type: string; current_index: number; total_files: number }) => void
      onFileComplete?: (data: { filename: string; output_filename: string; note_type: string; current_index: number; total_files: number; attempts: number; generation_time_seconds: number; note_content: string }) => void
      onFileFailed?: (data: { filename: string; output_filename: string; note_type: string; current_index: number; total_files: number; attempts: number; error_message: string }) => void
      onTotal?: (data: { filename: string; note_content: string }) => void
      onComplete?: (data: { total_files: number; processed: number; failed: number; total_time_seconds: number; results: any[] }) => void
      onError?: (detail: string) => void
    }
  ): { abort: () => void } => {
    const controller = new AbortController()
    const token = localStorage.getItem('access_token')
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    const url = baseUrl ? `${baseUrl}/api/v1/notes/batch-upload-process` : '/api/v1/notes/batch-upload-process'

    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }
    if (options.visitDate) {
      formData.append('visit_date', options.visitDate)
    }
    if (options.noteType) {
      formData.append('note_type_override', options.noteType)
    }

    fetch(url, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        // Do NOT set Content-Type — fetch sets it with boundary for FormData
      },
      body: formData,
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
          callbacks.onError?.(errData.detail || `HTTP ${response.status}`)
          return
        }

        const reader = response.body?.getReader()
        if (!reader) {
          callbacks.onError?.('No response stream available')
          return
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // SSE events are separated by \n\n
          // Split on double-newline to get complete events
          const events = buffer.split('\n\n')
          // Last element may be incomplete — keep it in buffer
          buffer = events.pop() || ''

          for (const eventBlock of events) {
            if (!eventBlock.trim()) continue

            let eventType = ''
            let dataLines: string[] = []

            for (const line of eventBlock.split('\n')) {
              if (line.startsWith('event: ')) {
                eventType = line.slice(7).trim()
              } else if (line.startsWith('data: ')) {
                dataLines.push(line.slice(6))
              } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5))
              }
            }

            if (eventType && dataLines.length > 0) {
              const eventData = dataLines.join('\n')
              try {
                const parsed = JSON.parse(eventData)
                switch (eventType) {
                  case 'file_start': callbacks.onFileStart?.(parsed); break
                  case 'file_complete': callbacks.onFileComplete?.(parsed); break
                  case 'file_failed': callbacks.onFileFailed?.(parsed); break
                  case 'total': callbacks.onTotal?.(parsed); break
                  case 'complete': callbacks.onComplete?.(parsed); break
                  case 'error': callbacks.onError?.(parsed.detail || 'Unknown error'); break
                }
              } catch (e) {
                console.warn('SSE parse error:', e, 'raw data:', eventData.slice(0, 200))
              }
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          callbacks.onError?.(err.message || 'Connection failed')
        }
      })

    return { abort: () => controller.abort() }
  },

  /**
   * Browse server-side directories for folder selection.
   * If no path provided, returns configured root directories.
   */
  browseDirectory: async (path?: string): Promise<BrowseDirectoryResponse> => {
    const response = await apiClient.get<BrowseDirectoryResponse>(
      '/notes/browse-directory',
      { params: path ? { path } : {} }
    )
    return response.data
  },

  /**
   * List processable files in a folder for batch processing preview.
   */
  listFolder: async (folderPath: string): Promise<BatchFolderListResponse> => {
    const response = await apiClient.get<BatchFolderListResponse>(
      '/notes/list-folder',
      { params: { folder_path: folderPath } }
    )
    return response.data
  },

  /**
   * Batch process a folder of clinical documents through Stage 1 → Stage 2.
   *
   * - Files with "CON" in the name → urology consult
   * - All other files → urology clinic note
   * - Retries up to 3 times per file on error
   * - Complete session purge between each patient (HIPAA)
   * - Creates total.vaucda concatenation at the end
   */
  batchProcess: async (request: BatchProcessingRequest): Promise<BatchProcessingResponse> => {
    const response = await apiClient.post<BatchProcessingResponse>(
      '/notes/batch-process',
      request,
      {
        timeout: 32400000, // 9 hours (10 files × 90 min max each)
      }
    )
    return response.data
  },

  /**
   * Batch process with SSE streaming for real-time per-file progress.
   *
   * Returns an EventSource-like interface. Caller handles events:
   * - progress: Per-file status update (BatchProgressEvent)
   * - complete: Final results (BatchProcessingResponse)
   * - error: Fatal error
   */
  batchProcessStream: (
    request: BatchProcessingRequest,
    onProgress: (event: BatchProgressEvent) => void,
    onComplete: (result: BatchProcessingResponse) => void,
    onError: (error: string) => void,
  ): { abort: () => void } => {
    const controller = new AbortController()
    const token = localStorage.getItem('access_token')
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    const url = baseUrl ? `${baseUrl}/api/v1/notes/batch-process-stream` : '/api/v1/notes/batch-process-stream'

    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: 'Batch processing failed' }))
          onError(errorData.detail || `HTTP ${response.status}`)
          return
        }

        const reader = response.body?.getReader()
        if (!reader) {
          onError('No response stream available')
          return
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // SSE events are separated by \n\n
          const events = buffer.split('\n\n')
          buffer = events.pop() || ''

          for (const eventBlock of events) {
            if (!eventBlock.trim()) continue

            let eventType = ''
            const dataLines: string[] = []

            for (const line of eventBlock.split('\n')) {
              if (line.startsWith('event: ')) {
                eventType = line.slice(7).trim()
              } else if (line.startsWith('data: ')) {
                dataLines.push(line.slice(6))
              } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5))
              }
            }

            if (eventType && dataLines.length > 0) {
              const eventData = dataLines.join('\n')
              try {
                const parsed = JSON.parse(eventData)
                if (eventType === 'progress') {
                  onProgress(parsed as BatchProgressEvent)
                } else if (eventType === 'complete') {
                  onComplete(parsed as BatchProcessingResponse)
                } else if (eventType === 'error') {
                  onError(parsed.detail || 'Unknown error')
                }
              } catch (e) {
                console.warn('SSE parse error:', e, 'raw data:', eventData.slice(0, 200))
              }
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          onError(err.message || 'Connection failed')
        }
      })

    return { abort: () => controller.abort() }
  },
}
