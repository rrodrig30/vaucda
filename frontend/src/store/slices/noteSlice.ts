import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import { notesApi } from '@/api'
import type { NoteGenerationRequest, NoteGenerationResponse } from '@/types/api.types'

interface NoteState {
  currentNote: NoteGenerationResponse | null
  // HIPAA COMPLIANCE: No savedNotes array - notes are ephemeral only
  isGenerating: boolean
  streamingContent: string
  streamingProgress: number
  error: string | null
}

const initialState: NoteState = {
  currentNote: null,
  // HIPAA COMPLIANCE: No note persistence
  isGenerating: false,
  streamingContent: '',
  streamingProgress: 0,
  error: null,
}

// Async thunks
export const generateNote = createAsyncThunk(
  'note/generate',
  async (request: NoteGenerationRequest, { rejectWithValue }) => {
    try {
      const response = await notesApi.generateNote(request)
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to generate note')
    }
  }
)

export const fetchNote = createAsyncThunk(
  'note/fetch',
  async (noteId: string, { rejectWithValue }) => {
    try {
      const response = await notesApi.getNote(noteId)
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to fetch note')
    }
  }
)

// HIPAA COMPLIANCE: fetchRecentNotes removed - notes are ephemeral only
// No note persistence or history retrieval to prevent cross-contamination

const noteSlice = createSlice({
  name: 'note',
  initialState,
  reducers: {
    clearCurrentNote: (state) => {
      state.currentNote = null
      state.streamingContent = ''
      state.streamingProgress = 0
    },
    appendStreamingContent: (state, action: PayloadAction<string>) => {
      state.streamingContent += action.payload
    },
    updateStreamingProgress: (state, action: PayloadAction<number>) => {
      state.streamingProgress = action.payload
    },
    resetStreaming: (state) => {
      state.streamingContent = ''
      state.streamingProgress = 0
      state.isGenerating = false
    },
    clearError: (state) => {
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      // Generate note
      .addCase(generateNote.pending, (state) => {
        state.isGenerating = true
        state.error = null
        state.streamingContent = ''
        state.streamingProgress = 0
      })
      .addCase(generateNote.fulfilled, (state, action) => {
        state.isGenerating = false
        state.currentNote = action.payload
        state.streamingProgress = 100
      })
      .addCase(generateNote.rejected, (state, action) => {
        state.isGenerating = false
        state.error = action.payload as string
      })
      // Fetch note
      .addCase(fetchNote.fulfilled, (state, action) => {
        // Convert SavedNote to NoteGenerationResponse format
        const savedNote = action.payload
        state.currentNote = {
          note_id: savedNote.note_id,
          generated_note: savedNote.generated_note,
          sections: [],
          appendices: [],
          metadata: {
            model_used: '',
            provider: '',
            tokens_used: 0,
            generation_time_ms: 0,
            modules_executed: 0,
            created_at: savedNote.created_at,
          },
        }
      })
      // HIPAA COMPLIANCE: No recent notes functionality - notes are ephemeral only
  },
})

export const {
  clearCurrentNote,
  appendStreamingContent,
  updateStreamingProgress,
  resetStreaming,
  clearError,
} = noteSlice.actions

export default noteSlice.reducer
