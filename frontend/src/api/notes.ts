import apiClient from './client'
import type {
  NoteGenerationRequest,
  NoteGenerationResponse,
  SavedNote,
  InitialNoteRequest,
  InitialNoteResponse,
  FinalNoteRequest,
  FinalNoteResponse,
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

  /**
   * Get recent notes for current user
   */
  getRecentNotes: async (limit: number = 10): Promise<SavedNote[]> => {
    const response = await apiClient.get<SavedNote[]>('/notes/recent', {
      params: { limit },
    })
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
}
